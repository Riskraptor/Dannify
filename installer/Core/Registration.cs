using System;
using System.Globalization;
using System.IO;
using Microsoft.Win32;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// What Windows is told about Dannify: the entry in Settings, Apps,
    /// double-clicking a saved song, and "dannify" in the Run box.
    /// Everything is per user (HKCU); nothing here needs an administrator.
    /// </summary>
    internal static class Registration
    {
        public const string ProgId = "Dannify.Track";

        public static void Write(Env env, string version, long bytes)
        {
            using (var k = Registry.CurrentUser.CreateSubKey(env.UninstallKey))
            {
                k.SetValue("DisplayName", "Dannify");
                k.SetValue("DisplayVersion", version);
                k.SetValue("Publisher", "Dannify");
                k.SetValue("DisplayIcon", env.LauncherExe + ",0");
                k.SetValue("InstallLocation", env.Root);
                k.SetValue("UninstallString", Quote(env.LauncherExe) + " --uninstall");
                k.SetValue("QuietUninstallString", Quote(env.LauncherExe) + " --uninstall --quiet");
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                k.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, bytes / 1024), RegistryValueKind.DWord);
                k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd", CultureInfo.InvariantCulture));
            }

            using (var k = Registry.CurrentUser.CreateSubKey(env.ClassesKey(".dnf")))
            {
                k.SetValue("", ProgId);
                using (var owp = k.CreateSubKey("OpenWithProgids")) owp.SetValue(ProgId, "");
            }
            using (var k = Registry.CurrentUser.CreateSubKey(env.ClassesKey(ProgId)))
                k.SetValue("", "Dannify song");
            using (var k = Registry.CurrentUser.CreateSubKey(env.ClassesKey(ProgId + @"\DefaultIcon")))
                k.SetValue("", env.LauncherExe + ",0");
            using (var k = Registry.CurrentUser.CreateSubKey(env.ClassesKey(ProgId + @"\shell\open\command")))
                k.SetValue("", Quote(env.LauncherExe) + " \"%1\"");
            using (var k = Registry.CurrentUser.CreateSubKey(env.ClassesKey(@"Applications\" + Env.ExeName + @"\SupportedTypes")))
                k.SetValue(".dnf", "");

            using (var k = Registry.CurrentUser.CreateSubKey(env.AppPathsKey))
            {
                k.SetValue("", env.LauncherExe);
                k.SetValue("Path", env.Root);
            }

            Notify(env);
        }

        /// <summary>Update what Settings shows after an update, and nothing else.</summary>
        public static void Refresh(Env env, string version, long bytes)
        {
            using (var k = Registry.CurrentUser.OpenSubKey(env.UninstallKey, true))
            {
                if (k == null) return;
                k.SetValue("DisplayVersion", version);
                k.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, bytes / 1024), RegistryValueKind.DWord);
            }
        }

        public static void RemoveLegacy(Env env)
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(env.LegacyUninstallKey, false);
            }
            catch (Exception ex)
            {
                Log.Warn("could not remove the old uninstall entry: " + ex.Message);
            }
        }

        public static void Remove(Env env)
        {
            TryDelete(env.UninstallKey);

            // The association is only removed while it is still ours: if the
            // user pointed .dnf somewhere else since, that choice stays.
            string command = ReadDefault(env.ClassesKey(ProgId + @"\shell\open\command"));
            if (command == null || command.IndexOf(env.Root, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                TryDelete(env.ClassesKey(ProgId));
                if (string.Equals(ReadDefault(env.ClassesKey(".dnf")), ProgId, StringComparison.OrdinalIgnoreCase))
                    TryDelete(env.ClassesKey(".dnf"));
                else
                    TryDeleteValue(env.ClassesKey(@".dnf\OpenWithProgids"), ProgId);
            }
            TryDelete(env.ClassesKey(@"Applications\" + Env.ExeName));

            string appPath = ReadDefault(env.AppPathsKey);
            if (appPath == null || appPath.IndexOf(env.Root, StringComparison.OrdinalIgnoreCase) >= 0)
                TryDelete(env.AppPathsKey);

            // Started with Windows (a setting in the app): only while it still
            // starts this copy, so a removed app does not leave a dead entry
            // in the Startup list.
            string run = ReadValue(env.RunKey, env.RunValueName);
            if (run != null && run.IndexOf(env.Root, StringComparison.OrdinalIgnoreCase) >= 0)
                TryDeleteValue(env.RunKey, env.RunValueName);

            Notify(env);
        }

        public static (string root, string version) ReadCurrent(Env env) => ReadInstall(Registry.CurrentUser, env.UninstallKey);

        public static (string root, string version) ReadLegacy(Env env) => ReadInstall(Registry.CurrentUser, env.LegacyUninstallKey);

        /// <summary>A copy installed for every user of the PC by an older Setup.</summary>
        public static (string root, string version) ReadLegacyMachine()
        {
            try
            {
                using (var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                    return ReadInstall(hklm, @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + Env.LegacyAppId);
            }
            catch
            {
                return (null, null);
            }
        }

        private static (string, string) ReadInstall(RegistryKey hive, string path)
        {
            try
            {
                using (var k = hive.OpenSubKey(path))
                {
                    if (k == null) return (null, null);
                    string root = (k.GetValue("InstallLocation") as string)?.Trim().TrimEnd('\\');
                    string version = k.GetValue("DisplayVersion") as string;
                    return (string.IsNullOrEmpty(root) ? null : root, version);
                }
            }
            catch
            {
                return (null, null);
            }
        }

        private static string ReadValue(string path, string name)
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(path)) return k?.GetValue(name) as string;
            }
            catch
            {
                return null;
            }
        }

        private static string ReadDefault(string path)
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(path)) return k?.GetValue("") as string;
            }
            catch
            {
                return null;
            }
        }

        private static void TryDelete(string path)
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(path, false);
            }
            catch (Exception ex)
            {
                Log.Warn("could not remove " + path + ": " + ex.Message);
            }
        }

        private static void TryDeleteValue(string path, string name)
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(path, true)) k?.DeleteValue(name, false);
            }
            catch
            {
                // nothing to do
            }
        }

        private static void Notify(Env env)
        {
            // Explorer caches file icons and associations; without this a .dnf
            // keeps its old blank icon until the next sign-in.
            if (!env.IsSandbox) Native.SHChangeNotify(Native.SHCNE_ASSOCCHANGED, 0, IntPtr.Zero, IntPtr.Zero);
        }

        private static string Quote(string path) => "\"" + path + "\"";
    }
}
