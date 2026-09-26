using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;

namespace Dannify.Setup.Core
{
    internal enum InstallKind
    {
        None,
        Current,        // this layout: launcher + app\
        Legacy,         // Dannify 3.x from the old Setup: the app straight in the folder
        LegacyMachine,  // 3.x installed for every user, in Program Files
    }

    /// <summary>What is already on this PC, and where.</summary>
    internal sealed class Existing
    {
        public InstallKind Kind;
        public string Root;
        public string Version;
        public bool HasDesktopShortcut;

        public bool IsInstalled => Kind != InstallKind.None;

        public static Existing Find(Env env, string preferredRoot)
        {
            var found = Probe(env, preferredRoot);
            if (found.Root != null)
            {
                string desktop = env.DesktopShortcut;
                found.HasDesktopShortcut = File.Exists(desktop) && Shortcuts.PointsInto(desktop, found.Root);
            }
            return found;
        }

        private static Existing Probe(Env env, string preferredRoot)
        {
            // An explicit folder wins: that is where this run was told to work.
            if (!string.IsNullOrEmpty(preferredRoot))
                return FromFolder(preferredRoot) ?? new Existing { Kind = InstallKind.None, Root = Path.GetFullPath(preferredRoot) };

            var (currentRoot, currentVersion) = Registration.ReadCurrent(env);
            if (currentRoot != null)
            {
                var hit = FromFolder(currentRoot);
                if (hit != null && hit.Kind == InstallKind.Current)
                {
                    hit.Version = hit.Version ?? currentVersion;
                    return hit;
                }
            }

            var (legacyRoot, legacyVersion) = Registration.ReadLegacy(env);
            if (legacyRoot != null)
            {
                var hit = FromFolder(legacyRoot);
                if (hit != null)
                {
                    hit.Version = hit.Version ?? legacyVersion;
                    return hit;
                }
            }

            if (!env.IsSandbox)
            {
                var byDefault = FromFolder(Env.DefaultRoot);
                if (byDefault != null) return byDefault;

                var (machineRoot, machineVersion) = Registration.ReadLegacyMachine();
                if (machineRoot != null && File.Exists(Path.Combine(machineRoot, Env.ExeName)))
                    return new Existing { Kind = InstallKind.LegacyMachine, Root = machineRoot, Version = machineVersion };
            }

            return new Existing { Kind = InstallKind.None };
        }

        /// <summary>Recognise an installation by what is in the folder.</summary>
        public static Existing FromFolder(string root)
        {
            try
            {
                root = Path.GetFullPath(root).TrimEnd('\\');
                string app = Path.Combine(root, "app", Env.ExeName);
                if (File.Exists(app))
                    return new Existing { Kind = InstallKind.Current, Root = root, Version = FileVersion(app) };
                if (Directory.Exists(Path.Combine(root, "app-next")) && File.Exists(Path.Combine(root, Env.ExeName)))
                    return new Existing { Kind = InstallKind.Current, Root = root };
                string legacy = Path.Combine(root, Env.ExeName);
                if (File.Exists(legacy) && Directory.Exists(Path.Combine(root, "runtime")))
                    return new Existing { Kind = InstallKind.Legacy, Root = root, Version = FileVersion(legacy) };
            }
            catch
            {
                // unreadable: treat as nothing there
            }
            return null;
        }

        public static string FileVersion(string exe)
        {
            try
            {
                var info = FileVersionInfo.GetVersionInfo(exe);
                string v = info.ProductVersion ?? info.FileVersion;
                return string.IsNullOrWhiteSpace(v) ? null : v.Trim();
            }
            catch
            {
                return null;
            }
        }

        /// <summary>Compare "3.18.1"-style versions; unparseable ones count as oldest.</summary>
        public static int Compare(string a, string b)
        {
            var va = Parse(a);
            var vb = Parse(b);
            for (int i = 0; i < 4; i++)
            {
                int c = va[i].CompareTo(vb[i]);
                if (c != 0) return c;
            }
            return 0;
        }

        private static int[] Parse(string v)
        {
            var parts = new int[4];
            if (string.IsNullOrEmpty(v)) return parts;
            var bits = v.Split('.', '-', '+', ' ');
            for (int i = 0, n = 0; i < bits.Length && n < 4; i++)
            {
                if (int.TryParse(bits[i], NumberStyles.Integer, CultureInfo.InvariantCulture, out int x)) parts[n++] = x;
                else break;
            }
            return parts;
        }
    }
}
