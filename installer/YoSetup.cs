// Per-user Ёхо (Yo-Voice) setup/uninstall stub (.NET Framework 4.5, C# 5).
// build-setup.ps1 compiles this as Uninstall.exe and, if Inno Setup is
// unavailable, as dist\Yo-Voice-Setup.exe with a zip payload appended:
//   [PE stub][zip of dist\Yo-Voice][uint64 zipLength][8 bytes YOVSETUP]

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class YoSetup
{
    const string AppIdName = "Yo-Voice";
    const string DisplayName = "\u0401\u0445\u043e (Yo-Voice)";
    const string ShortcutStem = "\u0401\u0445\u043e";
    const string Version = "1.0.0";
    const string Publisher = "iammedved";
    const string ExeName = "Yo-Voice.exe";
    const string RunValueName = "Yo-Voice";
    const string HelpUrl = "https://github.com/iammedved/Yo-Voice";
    static readonly byte[] Magic = Encoding.ASCII.GetBytes("YOVSETUP");

    static string InstallDir
    {
        get
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Yo-Voice");
        }
    }

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        bool silent = false;
        bool autostart = true;
        bool uninstall = false;
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if (string.Equals(a, "/S", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(a, "/SILENT", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(a, "/VERYSILENT", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(a, "--silent", StringComparison.OrdinalIgnoreCase))
                silent = true;
            else if (string.Equals(a, "/NOAUTOSTART", StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(a, "--no-autostart", StringComparison.OrdinalIgnoreCase))
                autostart = false;
            else if (string.Equals(a, "/UNINSTALL", StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(a, "--uninstall", StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(a, "uninstall", StringComparison.OrdinalIgnoreCase))
                uninstall = true;
        }

        string selfName = Path.GetFileName(SelfPath());
        if (string.Equals(selfName, "Uninstall.exe", StringComparison.OrdinalIgnoreCase))
            uninstall = true;

        try
        {
            if (uninstall)
                return RunUninstall(silent);
            return RunInstall(silent, autostart);
        }
        catch (Exception ex)
        {
            if (!silent)
                MessageBox.Show(ex.Message, DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static int RunInstall(bool silent, bool autostart)
    {
        long zipStart, zipLen;
        if (!TryGetPayload(out zipStart, out zipLen))
        {
            string msg = "This Setup.exe has no embedded app payload. Build with installer\\build-setup.ps1 after dist\\Yo-Voice\\Yo-Voice.exe exists.";
            if (!silent)
                MessageBox.Show(msg, DisplayName + " Setup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 2;
        }

        if (!silent)
        {
            using (InstallForm form = new InstallForm(InstallDir, autostart))
            {
                if (form.ShowDialog() != DialogResult.OK)
                    return 0;
                autostart = form.Autostart;
            }
        }

        StopApp();
        Directory.CreateDirectory(InstallDir);
        ExtractPayload(zipStart, zipLen, InstallDir);

        string exe = Path.Combine(InstallDir, ExeName);
        if (!File.Exists(exe))
            throw new InvalidOperationException("Extracted files are missing " + ExeName);

        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        Directory.CreateDirectory(programs);
        string comment = "\u0413\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0439 \u0432\u0432\u043e\u0434 \u0432 \u043b\u044e\u0431\u043e\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u043f\u043e\u043b\u0435";
        CreateShortcut(Path.Combine(programs, ShortcutStem + ".lnk"), exe, "", InstallDir, comment);
        CreateShortcut(Path.Combine(desktop, ShortcutStem + ".lnk"), exe, "", InstallDir, comment);

        SetAutostart(autostart, exe);
        WriteUninstallInfo(exe);
        CopyUninstallStub();

        if (!silent)
        {
            DialogResult launch = MessageBox.Show(
                DisplayName + " is installed.\r\n\r\nStart Menu and Desktop shortcuts: " + ShortcutStem +
                ".\r\nHotkey after launch: \u0451 or `.\r\n\r\nLaunch now?",
                DisplayName + " Setup",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information);
            if (launch == DialogResult.Yes)
                Process.Start(new ProcessStartInfo(exe, "daemon") { UseShellExecute = true, WorkingDirectory = InstallDir });
        }
        return 0;
    }

    static int RunUninstall(bool silent)
    {
        string appDir = InstallDir;
        string here = Path.GetDirectoryName(SelfPath());
        if (!string.IsNullOrEmpty(here) && File.Exists(Path.Combine(here, ExeName)))
            appDir = here;

        if (!silent)
        {
            DialogResult ok = MessageBox.Show(
                "Remove " + DisplayName + " from this computer?\r\n\r\nConfig (%APPDATA%\\yo-voice) and models (%LOCALAPPDATA%\\yo-voice) are kept.",
                DisplayName,
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);
            if (ok != DialogResult.Yes)
                return 0;
        }

        StopApp();

        string[] inno = Directory.Exists(appDir) ? Directory.GetFiles(appDir, "unins*.exe") : new string[0];
        if (inno.Length > 0)
        {
            ProcessStartInfo psi = new ProcessStartInfo(inno[0]);
            psi.UseShellExecute = true;
            if (silent)
                psi.Arguments = "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES";
            Process.Start(psi);
            return 0;
        }

        RemoveShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), ShortcutStem + ".lnk"));
        RemoveShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), ShortcutStem + ".lnk"));
        SetAutostart(false, null);
        try
        {
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppIdName, false);
        }
        catch (ArgumentException) { }

        try
        {
            if (Directory.Exists(appDir))
            {
                foreach (string f in Directory.GetFiles(appDir, "*", SearchOption.AllDirectories))
                {
                    try { File.SetAttributes(f, FileAttributes.Normal); File.Delete(f); }
                    catch { }
                }
            }
        }
        catch { }

        ProcessStartInfo rd = new ProcessStartInfo("cmd.exe");
        rd.Arguments = "/c ping 127.0.0.1 -n 3 > nul & rd /s /q \"" + appDir + "\"";
        rd.CreateNoWindow = true;
        rd.UseShellExecute = false;
        Process.Start(rd);
        return 0;
    }

    static void StopApp()
    {
        string exe = Path.Combine(InstallDir, ExeName);
        if (File.Exists(exe))
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(exe, "quit");
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.WorkingDirectory = InstallDir;
                Process p = Process.Start(psi);
                if (p != null)
                    p.WaitForExit(4000);
            }
            catch { }
        }
        foreach (Process p in Process.GetProcessesByName("Yo-Voice"))
        {
            try { p.Kill(); p.WaitForExit(3000); }
            catch { }
        }
        Thread.Sleep(400);
    }

    static void SetAutostart(bool enable, string exe)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run"))
        {
            if (key == null)
                return;
            if (enable && !string.IsNullOrEmpty(exe))
                key.SetValue(RunValueName, "\"" + exe + "\" daemon");
            else
            {
                try { key.DeleteValue(RunValueName, false); }
                catch (ArgumentException) { }
            }
        }
    }

    static void WriteUninstallInfo(string exe)
    {
        string uninst = Path.Combine(InstallDir, "Uninstall.exe");
        long sizeKb = 0;
        try
        {
            foreach (FileInfo fi in new DirectoryInfo(InstallDir).GetFiles("*", SearchOption.AllDirectories))
                sizeKb += fi.Length / 1024;
        }
        catch { }
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppIdName))
        {
            if (key == null)
                return;
            key.SetValue("DisplayName", DisplayName);
            key.SetValue("DisplayVersion", Version);
            key.SetValue("Publisher", Publisher);
            key.SetValue("InstallLocation", InstallDir);
            key.SetValue("UninstallString", "\"" + uninst + "\"");
            key.SetValue("QuietUninstallString", "\"" + uninst + "\" /S");
            key.SetValue("DisplayIcon", exe);
            key.SetValue("HelpLink", HelpUrl);
            key.SetValue("URLInfoAbout", HelpUrl);
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            key.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, sizeKb), RegistryValueKind.DWord);
        }
    }

    static void CopyUninstallStub()
    {
        string dest = Path.Combine(InstallDir, "Uninstall.exe");
        string self = SelfPath();
        long zipStart, zipLen;
        long stubLen = TryGetPayload(out zipStart, out zipLen) ? zipStart : new FileInfo(self).Length;
        byte[] buf = new byte[81920];
        using (FileStream src = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (FileStream dst = new FileStream(dest, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            long left = stubLen;
            while (left > 0)
            {
                int n = src.Read(buf, 0, (int)Math.Min(buf.Length, left));
                if (n <= 0)
                    break;
                dst.Write(buf, 0, n);
                left -= n;
            }
        }
    }

    static bool TryGetPayload(out long zipStart, out long zipLen)
    {
        zipStart = 0;
        zipLen = 0;
        string self = SelfPath();
        FileInfo fi = new FileInfo(self);
        if (fi.Length < 16)
            return false;
        using (FileStream fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            fs.Seek(-16, SeekOrigin.End);
            byte[] trailer = new byte[16];
            int n = fs.Read(trailer, 0, 16);
            if (n != 16)
                return false;
            for (int i = 0; i < 8; i++)
            {
                if (trailer[8 + i] != Magic[i])
                    return false;
            }
            zipLen = BitConverter.ToInt64(trailer, 0);
            if (zipLen <= 0 || zipLen > fi.Length - 16)
                return false;
            zipStart = fi.Length - 16 - zipLen;
            return zipStart >= 0;
        }
    }

    static void ExtractPayload(long zipStart, long zipLen, string dest)
    {
        string destFull = Path.GetFullPath(dest);
        if (!destFull.EndsWith(Path.DirectorySeparatorChar.ToString()))
            destFull += Path.DirectorySeparatorChar;
        using (FileStream fs = new FileStream(SelfPath(), FileMode.Open, FileAccess.Read, FileShare.Read))
        using (SliceStream slice = new SliceStream(fs, zipStart, zipLen))
        using (ZipArchive zip = new ZipArchive(slice, ZipArchiveMode.Read, true))
        {
            foreach (ZipArchiveEntry entry in zip.Entries)
            {
                string name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                string full = Path.GetFullPath(Path.Combine(dest, name));
                if (!full.StartsWith(destFull, StringComparison.OrdinalIgnoreCase))
                    continue;
                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(full);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(full));
                entry.ExtractToFile(full, true);
            }
        }
    }

    static void CreateShortcut(string lnkPath, string target, string args, string workDir, string desc)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        if (t == null)
            throw new InvalidOperationException("WScript.Shell is unavailable.");
        object shell = Activator.CreateInstance(t);
        object lnk = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { lnkPath });
        Type lt = lnk.GetType();
        lt.InvokeMember("TargetPath", BindingFlags.SetProperty, null, lnk, new object[] { target });
        lt.InvokeMember("Arguments", BindingFlags.SetProperty, null, lnk, new object[] { args ?? "" });
        lt.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, lnk, new object[] { workDir });
        lt.InvokeMember("Description", BindingFlags.SetProperty, null, lnk, new object[] { desc ?? "" });
        lt.InvokeMember("IconLocation", BindingFlags.SetProperty, null, lnk, new object[] { target + ",0" });
        lt.InvokeMember("Save", BindingFlags.InvokeMethod, null, lnk, null);
    }

    static void RemoveShortcut(string lnkPath)
    {
        try
        {
            if (File.Exists(lnkPath))
                File.Delete(lnkPath);
        }
        catch { }
    }

    static string SelfPath()
    {
        return Process.GetCurrentProcess().MainModule.FileName;
    }
}

sealed class InstallForm : Form
{
    readonly CheckBox _auto;

    public bool Autostart { get { return _auto.Checked; } }

    public InstallForm(string dest, bool autostartDefault)
    {
        Text = "\u0401\u0445\u043e (Yo-Voice) Setup";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(460, 200);
        Font = new Font("Segoe UI", 9f);

        Label body = new Label();
        body.Location = new Point(16, 16);
        body.Size = new Size(428, 80);
        body.Text = "Install \u0401\u0445\u043e (Yo-Voice) 1.0.0 for the current user (no administrator).\r\n\r\nLocation:\r\n" + dest;

        _auto = new CheckBox();
        _auto.Location = new Point(16, 108);
        _auto.Size = new Size(428, 24);
        _auto.Text = "Start \u0401\u0445\u043e at Windows logon (recommended)";
        _auto.Checked = autostartDefault;

        Button install = new Button();
        install.Text = "Install";
        install.DialogResult = DialogResult.OK;
        install.Location = new Point(252, 152);
        install.Size = new Size(90, 28);

        Button cancel = new Button();
        cancel.Text = "Cancel";
        cancel.DialogResult = DialogResult.Cancel;
        cancel.Location = new Point(354, 152);
        cancel.Size = new Size(90, 28);

        AcceptButton = install;
        CancelButton = cancel;
        Controls.Add(body);
        Controls.Add(_auto);
        Controls.Add(install);
        Controls.Add(cancel);
    }
}

sealed class SliceStream : Stream
{
    readonly Stream _inner;
    readonly long _start;
    readonly long _length;
    long _pos;

    public SliceStream(Stream inner, long start, long length)
    {
        _inner = inner;
        _start = start;
        _length = length;
        _pos = 0;
        _inner.Seek(_start, SeekOrigin.Begin);
    }

    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return _length; } }

    public override long Position
    {
        get { return _pos; }
        set { Seek(value, SeekOrigin.Begin); }
    }

    public override void Flush() { }

    public override int Read(byte[] buffer, int offset, int count)
    {
        long remain = _length - _pos;
        if (remain <= 0)
            return 0;
        if (count > remain)
            count = (int)remain;
        int n = _inner.Read(buffer, offset, count);
        _pos += n;
        return n;
    }

    public override long Seek(long offset, SeekOrigin origin)
    {
        long next = _pos;
        if (origin == SeekOrigin.Begin) next = offset;
        else if (origin == SeekOrigin.Current) next = _pos + offset;
        else if (origin == SeekOrigin.End) next = _length + offset;
        if (next < 0 || next > _length)
            throw new IOException("Seek out of slice.");
        _pos = next;
        _inner.Seek(_start + _pos, SeekOrigin.Begin);
        return _pos;
    }

    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
}
