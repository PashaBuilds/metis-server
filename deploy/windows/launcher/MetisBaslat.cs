// METIS-Baslat.exe — paket klasöründeki baslat.ps1'i çalıştırır (kurulum, yükseltme, başlatma, tarayıcıda açma).
// Tüm mantık baslat.ps1'dedir; bu dosya yalnız çift tıklanabilir bir giriş noktasıdır. Windows'taki .NET Framework
// derleyicisiyle (csc, C# 5) derlenir: deploy/build-bundle.py. Argümanlar baslat.ps1'e aynen geçer.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

[assembly: AssemblyTitle("METIS başlatıcı")]
[assembly: AssemblyProduct("METIS")]
[assembly: AssemblyDescription("METIS sunucusunu kurar veya başlatır ve tarayıcıda açar.")]

internal static class MetisBaslat
{
    // Yalnız MB_TOPMOST Windows 10'da pencereyi en üste almadı; MB_SYSTEMMODAL alıyor (bkz. baslat.ps1 Show-Message).
    private const uint MB_ICONERROR = 0x10, MB_ICONINFORMATION = 0x40, MB_SYSTEMMODAL = 0x1000, MB_SETFOREGROUND = 0x10000, MB_TOPMOST = 0x40000;

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    [DllImport("user32.dll")]
    private static extern bool AllowSetForegroundWindow(int processId);

    [STAThread]
    private static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(dir, "baslat.ps1");
        if (!File.Exists(script))
        {
            Show("baslat.ps1 bulunamadı. METIS-Baslat.exe, ZIP'ten çıkarılan paket klasörünün içinden çalıştırılmalı.\n\n" + dir, MB_ICONERROR);
            return 1;
        }
        // Tek kopya: soru ekrandayken yeniden çift tıklanırsa ikinci bir kurulum/yükseltme başlamasın.
        bool first;
        using (var mutex = new Mutex(true, "Local\\METIS-Baslat", out first))
        {
            if (!first)
            {
                Show("METIS başlatıcı zaten çalışıyor. Ekrandaki METIS penceresine bak (görev çubuğunda da görünür).", MB_ICONINFORMATION);
                return 3;
            }
            var line = new StringBuilder("-NoProfile -ExecutionPolicy Bypass -File " + Quote(script));
            foreach (string a in args) { line.Append(' ').Append(Quote(a)); }
            var psi = new ProcessStartInfo("powershell.exe", line.ToString());
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;  // sorular ileti kutusuyla sorulur; yönetici adımları kendi penceresinde görünür
            psi.WorkingDirectory = dir;
            // PowerShell 7 içinden açılınca devralınan PSModulePath, Windows PowerShell 5.1'in kendi modüllerini gölgeler
            // (Get-FileHash vb. bulunamaz). Değişken kaldırılınca 5.1 varsayılan yolunu kendisi kurar.
            psi.EnvironmentVariables.Remove("PSModulePath");
            try
            {
                using (Process p = Process.Start(psi))
                {
                    // Çift tıklanan exe öne gelme hakkına sahiptir; gizli PowerShell değildir. Hak devredilmezse ileti
                    // kutuları ve tarayıcı açık pencerelerin arkasında açılabilir.
                    AllowSetForegroundWindow(p.Id);
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
            catch (Exception e)
            {
                Show("PowerShell başlatılamadı: " + e.Message, MB_ICONERROR);
                return 1;
            }
        }
    }

    private static void Show(string text, uint icon)
    {
        MessageBoxW(IntPtr.Zero, text, "METIS", icon | MB_SYSTEMMODAL | MB_SETFOREGROUND | MB_TOPMOST);
    }

    private static string Quote(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) { return s; }
        return "\"" + s.Replace("\"", "\\\"") + "\"";
    }
}
