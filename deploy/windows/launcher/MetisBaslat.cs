// METIS-Baslat.exe — paket klasöründeki baslat.ps1'i çalıştırır (kurulum, yükseltme, başlatma, tarayıcıda açma).
// Tüm mantık baslat.ps1'dedir; bu dosya yalnız çift tıklanabilir bir giriş noktasıdır. Windows'taki .NET Framework
// derleyicisiyle (csc, C# 5) CI'da derlenir: deploy/build-bundle.py. Argümanlar baslat.ps1'e aynen geçer.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("METIS başlatıcı")]
[assembly: AssemblyProduct("METIS")]
[assembly: AssemblyDescription("METIS sunucusunu kurar veya başlatır ve tarayıcıda açar.")]

internal static class MetisBaslat
{
    [STAThread]
    private static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(dir, "baslat.ps1");
        if (!File.Exists(script))
        {
            MessageBox.Show("baslat.ps1 bulunamadı. METIS-Baslat.exe, ZIP'ten çıkarılan paket klasörünün içinden çalıştırılmalı.\n\n" + dir,
                "METIS", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
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
                p.WaitForExit();
                return p.ExitCode;
            }
        }
        catch (Exception e)
        {
            MessageBox.Show("PowerShell başlatılamadı: " + e.Message, "METIS", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string Quote(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) { return s; }
        return "\"" + s.Replace("\"", "\\\"") + "\"";
    }
}
