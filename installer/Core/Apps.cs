using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace Dannify.Setup.Core
{
    /// <summary>Finding, asking and (only if it must) stopping running copies.</summary>
    internal static class Apps
    {
        private static readonly int Self = Process.GetCurrentProcess().Id;

        /// <summary>
        /// Processes whose program file is inside <paramref name="dir"/>. This is
        /// how "is Dannify running from here" is answered: never by name, so a
        /// copy somewhere else, or anything else called Dannify.exe, is left
        /// alone.
        /// </summary>
        public static List<int> ProcessesUnder(string dir, int alsoExclude = -1)
        {
            var found = new List<int>();
            if (string.IsNullOrEmpty(dir)) return found;
            string prefix;
            try
            {
                prefix = Path.GetFullPath(dir).TrimEnd('\\') + "\\";
            }
            catch
            {
                return found;
            }
            foreach (var p in Process.GetProcesses())
            {
                try
                {
                    int pid = p.Id;
                    if (pid == Self || pid == alsoExclude || pid <= 4) continue;
                    string image = ImagePath(pid);
                    if (image != null && image.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        found.Add(pid);
                }
                catch
                {
                    // Gone, or not ours to look at.
                }
                finally
                {
                    p.Dispose();
                }
            }
            return found;
        }

        public static string ImagePath(int pid)
        {
            IntPtr h = Native.OpenProcess(Native.PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
            if (h == IntPtr.Zero) return null;
            try
            {
                var sb = new StringBuilder(1024);
                int size = sb.Capacity;
                return Native.QueryFullProcessImageNameW(h, 0, sb, ref size) ? sb.ToString(0, size) : null;
            }
            finally
            {
                Native.CloseHandle(h);
            }
        }

        public static bool MutexExists(string name)
        {
            IntPtr h = Native.OpenMutexW(Native.SYNCHRONIZE, false, name);
            if (h == IntPtr.Zero) return false;
            Native.CloseHandle(h);
            return true;
        }

        /// <summary>
        /// Ask a running copy to quit properly: saving where it was, closing
        /// its files. Closing its window would not do: close-to-tray hides it.
        /// </summary>
        public static bool RequestQuit(string eventName)
        {
            IntPtr h = Native.OpenEventW(Native.EVENT_MODIFY_STATE, false, eventName);
            if (h == IntPtr.Zero) return false;
            try
            {
                return Native.SetEvent(h);
            }
            finally
            {
                Native.CloseHandle(h);
            }
        }

        public static bool WaitUntil(Func<bool> done, int timeoutMs, CancellationToken ct, int pollMs = 150)
        {
            var sw = Stopwatch.StartNew();
            while (true)
            {
                if (done()) return true;
                if (sw.ElapsedMilliseconds >= timeoutMs) return false;
                ct.ThrowIfCancellationRequested();
                Thread.Sleep(pollMs);
            }
        }

        /// <summary>True once <paramref name="pid"/> has exited (or never existed).</summary>
        public static bool WaitForExit(int pid, int timeoutMs)
        {
            IntPtr h = Native.OpenProcess(Native.SYNCHRONIZE, false, pid);
            if (h == IntPtr.Zero) return true;
            try
            {
                return Native.WaitForSingleObject(h, (uint)Math.Max(0, timeoutMs)) != Native.WAIT_TIMEOUT;
            }
            finally
            {
                Native.CloseHandle(h);
            }
        }

        public static void Kill(IEnumerable<int> pids)
        {
            foreach (int pid in pids)
            {
                IntPtr h = Native.OpenProcess(Native.PROCESS_TERMINATE | Native.SYNCHRONIZE, false, pid);
                if (h == IntPtr.Zero) continue;
                try
                {
                    Log.Warn("stopping process " + pid + " (" + ImagePath(pid) + ")");
                    Native.TerminateProcess(h, 1);
                    Native.WaitForSingleObject(h, 3000);
                }
                finally
                {
                    Native.CloseHandle(h);
                }
            }
        }

        /// <summary>
        /// Close whatever runs from <paramref name="root"/>: ask first, wait,
        /// and only then, if <paramref name="mayForce"/> allows or
        /// <paramref name="askToForce"/> says yes, stop it.
        /// </summary>
        public static void CloseAll(Env env, string root, bool mayForce, Func<bool> askToForce, CancellationToken ct)
        {
            bool Running() => ProcessesUnder(root).Count > 0;
            if (!Running()) return;

            Log.Info("asking the running copy to quit");
            RequestQuit(env.QuitEventName);
            if (WaitUntil(() => !Running(), 15000, ct)) return;

            if (!mayForce && !(askToForce?.Invoke() ?? false))
                throw new SetupException(Problem.StillRunning);
            Kill(ProcessesUnder(root));
            if (!WaitUntil(() => !Running(), 6000, ct))
                throw new SetupException(Problem.StillRunning);
        }
    }
}
