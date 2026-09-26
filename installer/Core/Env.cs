using System;
using System.Diagnostics;
using System.IO;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// Where everything lives.
    ///
    ///   &lt;root&gt;\Dannify.exe     this program, as launcher and uninstaller
    ///   &lt;root&gt;\app\            the app itself (always this path: Windows keys
    ///                          the tray icon's "always show" choice, firewall
    ///                          and volume settings on the program's path)
    ///   &lt;root&gt;\app-next\       an update waiting for the next start
    ///
    /// A sandbox (--sandbox NAME, tests only) moves every registry key under
    /// HKCU\Software\DannifySetupTest\NAME and every shortcut into a folder
    /// beside the root, so a test can never touch a real installation.
    /// </summary>
    internal sealed class Env
    {
        public const string Aumid = "Dannify.Player";
        public const string LegacyAppId = "{7E1D8F0C-5A53-4D7B-9C2B-DA221F900001}_is1";
        public const string ExeName = "Dannify.exe";

        public static readonly string SelfPath = FindSelf();

        public string Root;
        public string DataDir;
        public string Instance = "";
        public string SandboxName;
        public string StartMenuPrograms;
        public string DesktopDir;

        public bool IsSandbox => SandboxName != null;
        public string AppDir => Path.Combine(Root, "app");
        public string NextDir => Path.Combine(Root, "app-next");
        public string AppExe => Path.Combine(AppDir, ExeName);
        public string LauncherExe => Path.Combine(Root, ExeName);
        public string StartShortcut => Path.Combine(StartMenuPrograms, "Dannify.lnk");
        public string DesktopShortcut => Path.Combine(DesktopDir, "Dannify.lnk");
        public string LegacyStartFolder => Path.Combine(StartMenuPrograms, "Dannify");
        public string MutexName => @"Local\DannifyAppMutex" + Instance;
        public string QuitEventName => @"Local\DannifyQuitRequest" + Instance;

        private string SandboxKey => @"Software\DannifySetupTest\" + SandboxName + @"\";

        public string UninstallKey => IsSandbox
            ? SandboxKey + @"Uninstall\Dannify"
            : @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Dannify";

        public string LegacyUninstallKey => IsSandbox
            ? SandboxKey + @"Uninstall\" + LegacyAppId
            : @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + LegacyAppId;

        public string AppPathsKey => IsSandbox
            ? SandboxKey + @"App Paths\" + ExeName
            : @"Software\Microsoft\Windows\CurrentVersion\App Paths\" + ExeName;

        public string ClassesKey(string sub) => IsSandbox ? SandboxKey + @"Classes\" + sub : @"Software\Classes\" + sub;

        public static string LocalAppData => Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        public static string DefaultRoot => Path.Combine(LocalAppData, "Programs", "Dannify");
        public static string DefaultData => Path.Combine(LocalAppData, "Dannify");

        private static string FindSelf()
        {
            try
            {
                using (var p = Process.GetCurrentProcess()) return p.MainModule.FileName;
            }
            catch
            {
                return typeof(Env).Assembly.Location;
            }
        }

        /// <summary>
        /// <paramref name="root"/> is where this run works: the launcher's own
        /// folder, or whatever the installer decided on (it may change later,
        /// when the user picks another folder).
        /// </summary>
        public static Env Create(Args args, string root)
        {
            var env = new Env { SandboxName = string.IsNullOrWhiteSpace(args.Sandbox) ? null : args.Sandbox.Trim() };
            env.Root = string.IsNullOrEmpty(root) ? null : Path.GetFullPath(root);

            string envData = Environment.GetEnvironmentVariable("DANNIFY_DATA_DIR");
            string envInstance = Environment.GetEnvironmentVariable("DANNIFY_INSTANCE");

            if (env.IsSandbox)
            {
                if (env.Root == null) throw new InvalidOperationException("a sandbox needs --root");
                string side = env.Root.TrimEnd('\\') + ".sandbox";
                env.StartMenuPrograms = Path.Combine(side, "Programs");
                env.DesktopDir = Path.Combine(side, "Desktop");
                env.DataDir = args.Data ?? envData ?? Path.Combine(side, "data");
                env.Instance = args.Instance ?? envInstance ?? ("sandbox-" + env.SandboxName);
            }
            else
            {
                env.StartMenuPrograms = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                env.DesktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                env.DataDir = args.Data ?? envData ?? DefaultData;
                env.Instance = args.Instance ?? envInstance ?? "";
            }
            return env;
        }

        /// <summary>
        /// Environment for the app when this program starts it. In a sandbox
        /// the app is pinned to the sandbox's data and music folders and to a
        /// mutex of its own, so it cannot reach a real library or collide with
        /// a copy the user has open.
        /// </summary>
        public void Prepare(ProcessStartInfo psi)
        {
            psi.EnvironmentVariables["DANNIFY_LAUNCHER"] = LauncherExe;
            if (!IsSandbox) return;
            string side = Root.TrimEnd('\\') + ".sandbox";
            psi.EnvironmentVariables["DANNIFY_DATA_DIR"] = DataDir;
            psi.EnvironmentVariables["DOWNLOAD_DIR"] = Environment.GetEnvironmentVariable("DOWNLOAD_DIR") ?? Path.Combine(side, "Music");
            psi.EnvironmentVariables["DANNIFY_INSTANCE"] = Instance;
        }
    }
}
