"""Предзагрузка русской модели Whisper. Процент считается только из байтов.

Каталог тот же, что у snapshot_download в работающем приложении: yo.__main__
делает setdefault HF_HOME = xdg_cache()/hf, а huggingface_hub кладёт репозитории
в HF_HUB_CACHE (HF_HOME/hub). Это не каталог перевода yo.mt (xdg_cache()/huggingface).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from yo.asr import DEFAULT_MODEL, RU_TURBO_CT2

# Тот же repo id, что грузит AsrEngine, если в конфиге не задана другая модель.
WHISPER_REPO = DEFAULT_MODEL
# resolve_whisper_path качает только этот каталог, не корень репозитория.
WHISPER_ALLOW = (f"{RU_TURBO_CT2}/*",)

# Картинки карточки и .gitattributes faster-whisper не читает — в сумму байтов не входят.
# Сейчас в ct2_int8_float16 их нет: в сумме config.json, model.bin,
# preprocessor_config.json, tokenizer.json, vocabulary.json.
# Мимо остаются README, корневые json, model.safetensors и ct2-int16/.
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico")

ProgressFn = Callable[[int, int, str], None]


class PrefetchError(Exception):
    """Сеть или Hub не отдали модель. Исходное исключение лежит в __cause__."""


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int


@dataclass(frozen=True)
class PrefetchResult:
    already_present: bool
    total_bytes: int
    cache_dir: Path
    model_dir: Path
    files: tuple[str, ...]
    checked_at: float | None = None


def percent(done: int, total: int) -> int:
    """1..99 пока байты в пути, 100 только когда done >= total > 0.

    Пока общий размер неизвестен (total <= 0) — 1. Ноль не возвращается.
    """
    if total <= 0:
        return 1
    if done >= total:
        return 100
    if done <= 0:
        return 1
    value = (int(done) * 100) // int(total)
    if value < 1:
        return 1
    if value > 99:
        return 99
    return value


def whisper_cache_dir() -> Path:
    """Каталог hub, куда asr.snapshot_download пишет модель без своего cache_dir."""
    _align_hub_env()
    explicit = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return _expand(explicit)
    home = os.environ.get("HF_HOME")
    if not home:
        from yo.paths import xdg_cache

        home = str(xdg_cache() / "hf")
        os.environ["HF_HOME"] = home
    return _expand(home) / "hub"


def remote_byte_size(entry: object) -> int:
    """Размер файла с Hub. У LFS берём lfs.size, а не указатель в git (~134 байта)."""
    lfs = getattr(entry, "lfs", None)
    lfs_size = getattr(lfs, "size", None) if lfs is not None else None
    if lfs_size is not None:
        return int(lfs_size)
    size = getattr(entry, "size", None)
    if size is None:
        path = getattr(entry, "path", "?")
        raise PrefetchError(f"Hub не сообщил размер файла {path}.")
    return int(size)


def select_whisper_files(files: Iterable[RemoteFile]) -> tuple[RemoteFile, ...]:
    """Файлы, которые snapshot_download заберёт для faster-whisper, без картинок и git."""
    from huggingface_hub.utils import filter_repo_objects

    incoming = list(files)
    allowed = set(
        filter_repo_objects((item.path.replace("\\", "/") for item in incoming), allow_patterns=list(WHISPER_ALLOW))
    )
    chosen: list[RemoteFile] = []
    seen: set[str] = set()
    for item in incoming:
        path = item.path.replace("\\", "/")
        if path not in allowed or path in seen or _ignored_by_app(path):
            continue
        if item.size < 0:
            raise PrefetchError(f"Hub сообщил странный размер файла {path}.")
        seen.add(path)
        chosen.append(RemoteFile(path, int(item.size)))
    chosen.sort(key=lambda item: item.path)
    return tuple(chosen)


def remote_whisper_files() -> tuple[RemoteFile, ...]:
    """Имена и размеры с API метаданных Hub. Сами веса не качает."""
    _align_hub_env()
    from huggingface_hub import HfApi, RepoFile

    listed: list[RemoteFile] = []
    for entry in HfApi().list_repo_tree(WHISPER_REPO, recursive=True, revision="main"):
        if not isinstance(entry, RepoFile):
            continue
        listed.append(RemoteFile(entry.path, remote_byte_size(entry)))
    return select_whisper_files(listed)


def download_whisper_file(
    filename: str,
    *,
    cache_dir: Path,
    tqdm_class: type,
    force: bool = False,
) -> str:
    """Один файл через hf_hub_download: докачка и блокировка — на стороне библиотеки."""
    _align_hub_env()
    import huggingface_hub

    return huggingface_hub.hf_hub_download(
        WHISPER_REPO,
        filename,
        revision="main",
        cache_dir=str(cache_dir),
        force_download=force,
        tqdm_class=tqdm_class,
    )


def prefetch_whisper(on_progress: ProgressFn, *, now: float | None = None) -> PrefetchResult:
    """Скачать модель, если локальные размеры не совпали с Hub.

    on_progress(done_bytes, total_bytes, phase). phase — "download", пока идут
    байты, и "check", когда готовые файлы сверены с диском. `now` только
    попадает в результат и на процент не влияет.
    """
    cache_dir = whisper_cache_dir()
    try:
        files = select_whisper_files(remote_whisper_files())
    except PrefetchError:
        raise
    except Exception as exc:
        # Сеть метаданных недоступна. Если веса уже целые, не качаем заново.
        local = _offline_ready(cache_dir, now)
        if local is not None:
            state: dict = {"last": -1, "callback_error": None}
            _call_progress(on_progress, local.total_bytes, local.total_bytes, "check", state)
            return local
        raise PrefetchError("Не удалось узнать размер модели. Проверьте сеть.") from exc

    _require_weights(files)
    total = sum(item.size for item in files)
    state: dict = {"last": -1, "callback_error": None}
    matched, pending = _split_present(files, cache_dir)
    if not pending:
        model_dir = _verified_model_dir(files, cache_dir)
        _call_progress(on_progress, total, total, "check", state)
        return _result(files, cache_dir, model_dir, total, already_present=True, now=now)

    base = sum(item.size for item in matched)
    for item in pending:
        local_size = _local_size(item.path, cache_dir)
        bar = _download_bar(base, item.size, total, on_progress, state)
        try:
            download_whisper_file(
                item.path,
                cache_dir=cache_dir,
                tqdm_class=bar,
                force=local_size is not None,
            )
        except PrefetchError:
            raise
        except Exception as exc:
            if state.get("callback_error") is exc:
                raise
            raise PrefetchError("Не удалось скачать модель распознавания.") from exc
        base += item.size
        # Докачанный файл целиком, если tqdm не дошёл до его размера.
        _emit_download(base, total, on_progress, state)

    model_dir = _verified_model_dir(files, cache_dir)
    _call_progress(on_progress, total, total, "check", state)
    return _result(files, cache_dir, model_dir, total, already_present=False, now=now)


def _result(
    files: tuple[RemoteFile, ...],
    cache_dir: Path,
    model_dir: Path,
    total: int,
    *,
    already_present: bool,
    now: float | None,
) -> PrefetchResult:
    return PrefetchResult(
        already_present=already_present,
        total_bytes=total,
        cache_dir=cache_dir,
        model_dir=model_dir,
        files=tuple(item.path for item in files),
        checked_at=now,
    )


# Ниже этого model.bin ещё не тот снимок, который читает faster-whisper.
_MIN_WEIGHTS = 700_000_000
_READY_NAMES = (
    f"{RU_TURBO_CT2}/config.json",
    f"{RU_TURBO_CT2}/model.bin",
    f"{RU_TURBO_CT2}/preprocessor_config.json",
    f"{RU_TURBO_CT2}/tokenizer.json",
    f"{RU_TURBO_CT2}/vocabulary.json",
)


def weights_ready() -> bool:
    """Локальная проверка без Hub. Нужна, чтобы не крутить окно и не перезапускаться зря."""
    try:
        return _offline_ready(whisper_cache_dir(), None) is not None
    except Exception:
        return False


def _offline_ready(cache_dir: Path, now: float | None) -> PrefetchResult | None:
    found: list[RemoteFile] = []
    for name in _READY_NAMES:
        try:
            size = _local_size(name, cache_dir)
        except Exception:
            return None
        if size is None or size <= 0:
            return None
        if name.endswith("/model.bin") and size < _MIN_WEIGHTS:
            return None
        found.append(RemoteFile(name, int(size)))
    chosen = tuple(found)
    try:
        model_dir = _verified_model_dir(chosen, cache_dir)
    except Exception:
        return None
    return _result(
        chosen,
        cache_dir,
        model_dir,
        sum(item.size for item in chosen),
        already_present=True,
        now=now,
    )


def _require_weights(files: tuple[RemoteFile, ...]) -> None:
    if not files or sum(item.size for item in files) <= 0:
        raise PrefetchError("На Hub нет файлов модели распознавания.")
    if not any(Path(item.path).name == "model.bin" for item in files):
        raise PrefetchError("На Hub нет файла весов модели.")


def _split_present(files: tuple[RemoteFile, ...], cache_dir: Path) -> tuple[list[RemoteFile], list[RemoteFile]]:
    matched: list[RemoteFile] = []
    pending: list[RemoteFile] = []
    for item in files:
        if _local_size(item.path, cache_dir) == item.size:
            matched.append(item)
        else:
            pending.append(item)
    return matched, pending


def _local_file(filename: str, cache_dir: Path) -> Path | None:
    _align_hub_env()
    from huggingface_hub import try_to_load_from_cache

    found = try_to_load_from_cache(
        WHISPER_REPO,
        filename,
        cache_dir=str(cache_dir),
        revision="main",
    )
    if not isinstance(found, str):
        return None
    path = Path(found)
    if not path.is_file():
        return None
    return path


def _local_size(filename: str, cache_dir: Path) -> int | None:
    path = _local_file(filename, cache_dir)
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def _verified_model_dir(files: tuple[RemoteFile, ...], cache_dir: Path) -> Path:
    weights_dir: Path | None = None
    for item in files:
        path = _local_file(item.path, cache_dir)
        if path is None:
            raise PrefetchError("Файл модели на диске не совпал с размером на Hub.")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PrefetchError("Файл модели на диске не совпал с размером на Hub.") from exc
        if size != item.size:
            raise PrefetchError("Файл модели на диске не совпал с размером на Hub.")
        if Path(item.path).name == "model.bin":
            weights_dir = _model_dir(path)
    if weights_dir is None:
        raise PrefetchError("На Hub нет файла весов модели.")
    return weights_dir


def _model_dir(local_file: Path) -> Path:
    for parent in local_file.parents:
        if parent.name == RU_TURBO_CT2:
            return parent
    return local_file.parent


def _emit_download(done: int, total: int, on_progress: ProgressFn, state: dict) -> None:
    # 100 только после сверки на диске: в фазе download done не достигает total.
    reported = total - 1 if total > 0 and done >= total else done
    if reported <= 0 or reported <= state["last"]:
        return
    state["last"] = reported
    _call_progress(on_progress, reported, total, "download", state)


def _call_progress(on_progress: ProgressFn, done: int, total: int, phase: str, state: dict) -> None:
    try:
        on_progress(int(done), int(total), phase)
    except Exception as exc:
        state["callback_error"] = exc
        raise


def _download_bar(base: int, file_size: int, total: int, on_progress: ProgressFn, state: dict) -> type:
    """tqdm-класс на один файл: n — байты этого файла, наружу уходит сумма."""

    class _FileBytes:
        def __init__(self, *args: object, initial: int = 0, **kwargs: object) -> None:
            self.n = int(initial or 0)
            self._push()

        def _push(self) -> None:
            shown = self.n
            if shown < 0:
                shown = 0
            elif file_size >= 0 and shown > file_size:
                shown = file_size
            _emit_download(base + shown, total, on_progress, state)

        def update(self, n: int | float | None = 1) -> None:
            if n is None:
                n = 1
            self.n += int(n)
            self._push()

        def __enter__(self) -> _FileBytes:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def close(self) -> None:
            return None

    return _FileBytes


def _ignored_by_app(repo_path: str) -> bool:
    name = repo_path.rsplit("/", 1)[-1].lower()
    if name == ".gitattributes":
        return True
    return name.endswith(_IMAGE_SUFFIXES)


def _expand(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value)))


def _align_hub_env() -> None:
    # Как yo.__main__ до импорта huggingface_hub: HTTP-докачка, не Xet.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
