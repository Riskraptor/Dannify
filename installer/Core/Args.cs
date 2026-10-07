using System;
using System.Collections.Generic;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// The command line, for every role this program plays.
    ///
    /// Copies of Dannify up to 3.18 hand a downloaded installer Inno Setup's
    /// switches (/VERYSILENT /SUPPRESSMSGBOXES /NORESTART when the app closes
    /// with an update waiting), so those are understood here too. Anything not
    /// recognised is kept, in order, for the app itself: the launcher passes it
    /// straight through (a .dnf opened from Explorer, --quit, and so on).
    /// </summary>
    internal sealed class Args
    {
        public bool Quiet;          // no window at all
        public bool ProgressOnly;   // just a small progress window
        public bool Update;         // an update: progress only, then open the app
        public bool Uninstall;
        public bool VerifyPayload;  // build check: unpack in memory and verify, touch nothing
        public bool? Launch;
        public bool? DesktopShortcut;
        public int AfterPid;
        public string Root;
        public string Data;
        public string Sandbox;
        public string Instance;
        public string Lang;
        public string UiState;
        public string RemoveMachineCopy;
        public string UnpackTo;
        public string WriteEngineTo; // build check: the launcher copy an install would leave
        public readonly List<string> PassThrough = new List<string>();

        private static readonly HashSet<string> InnoIgnored = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "/suppressmsgboxes", "/norestart", "/sp-", "/nocancel", "/noicons",
            "/closeapplications", "/nocloseapplications", "/forcecloseapplications",
            "/noforcecloseapplications", "/restartapplications", "/norestartapplications",
            "/currentuser", "/allusers", "/log",
        };

        public static Args Parse(string[] argv)
        {
            var a = new Args();
            for (int i = 0; i < argv.Length; i++)
            {
                string raw = argv[i] ?? "";
                string arg = raw.Trim();
                string lower = arg.ToLowerInvariant();

                string Next() => i + 1 < argv.Length ? argv[++i] : null;

                switch (lower)
                {
                    case "/verysilent":
                    case "/quiet":
                    case "--quiet":
                    case "-q":
                        a.Quiet = true;
                        continue;
                    case "/silent":
                        a.ProgressOnly = true;
                        continue;
                    case "--update":
                        a.Update = true;
                        a.ProgressOnly = true;
                        continue;
                    case "--launch":
                        a.Launch = true;
                        continue;
                    case "--no-launch":
                        a.Launch = false;
                        continue;
                    case "--uninstall":
                        a.Uninstall = true;
                        continue;
                    case "--desktop-shortcut":
                        a.DesktopShortcut = true;
                        continue;
                    case "--no-desktop-shortcut":
                        a.DesktopShortcut = false;
                        continue;
                    case "--verify-payload":
                        a.VerifyPayload = true;
                        continue;
                    case "--after":
                        int.TryParse(Next(), out a.AfterPid);
                        continue;
                    case "--root":
                        a.Root = Next();
                        continue;
                    case "--data":
                        a.Data = Next();
                        continue;
                    case "--sandbox":
                        a.Sandbox = Next();
                        continue;
                    case "--instance":
                        a.Instance = Next();
                        continue;
                    case "--lang":
                        a.Lang = Next();
                        continue;
                    case "--ui-state":
                        a.UiState = Next();
                        continue;
                    case "--remove-machine-copy":
                        a.RemoveMachineCopy = Next();
                        continue;
                    case "--unpack-to":
                        a.UnpackTo = Next();
                        continue;
                    case "--write-engine":
                        a.WriteEngineTo = Next();
                        continue;
                }

                if (lower.StartsWith("/dir=", StringComparison.Ordinal))
                {
                    a.Root = arg.Substring(5).Trim('"');
                    continue;
                }
                if (lower.StartsWith("/lang=", StringComparison.Ordinal))
                {
                    a.Lang = arg.Substring(6).Trim('"');
                    continue;
                }
                if (lower.StartsWith("/tasks=", StringComparison.Ordinal) ||
                    lower.StartsWith("/mergetasks=", StringComparison.Ordinal))
                {
                    string list = lower.Substring(lower.IndexOf('=') + 1).Trim('"');
                    foreach (var task in list.Split(','))
                    {
                        string t = task.Trim();
                        if (t == "desktopicon") a.DesktopShortcut = true;
                        else if (t == "!desktopicon") a.DesktopShortcut = false;
                    }
                    continue;
                }
                if (lower.StartsWith("/log=", StringComparison.Ordinal) || InnoIgnored.Contains(lower))
                    continue;

                a.PassThrough.Add(raw);
            }
            return a;
        }
    }
}
