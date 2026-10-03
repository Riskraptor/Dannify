using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// File moves and deletes that ride out Windows holding a file for a
    /// moment: the virus scanner looking over a program that just stopped,
    /// or the search indexer. Those clear up in seconds; a first attempt that
    /// gives up straight away turns bad timing into a failed install.
    /// </summary>
    internal static class Files
    {
        private static bool IsBusy(Exception ex)
        {
            if (ex is UnauthorizedAccessException) return true;
            if (ex is IOException io)
            {
                int code = io.HResult & 0xFFFF;
                return code == 5 || code == 32 || code == 33;
            }
            return false;
        }

        private static void Patient(Action act, int patienceMs)
        {
            var sw = Stopwatch.StartNew();
            int pause = 100;
            while (true)
            {
                try
                {
                    act();
                    return;
                }
                catch (Exception ex) when (IsBusy(ex) && sw.ElapsedMilliseconds < patienceMs)
                {
                    Thread.Sleep(pause);
                    pause = Math.Min(pause * 2, 1000);
                }
            }
        }

        /// <summary>
        /// A file opened the same patient way. Unpacking writes a couple of
        /// hundred new programs and libraries, and the virus scanner looks
        /// over each one as it is closed: one still being looked at when it
        /// was opened again could fail the whole install a few seconds in.
        /// </summary>
        public static FileStream Open(string path, FileMode mode, FileAccess access, FileShare share,
            int bufferSize = 4096, int patienceMs = 8000)
        {
            FileStream fs = null;
            Patient(() => fs = new FileStream(path, mode, access, share, bufferSize), patienceMs);
            return fs;
        }

        public static void MoveDir(string src, string dst, int patienceMs = 10000) =>
            Patient(() => Directory.Move(src, dst), patienceMs);

        public static void MoveFile(string src, string dst, int patienceMs = 10000) =>
            Patient(() => File.Move(src, dst), patienceMs);

        /// <summary><paramref name="basePath"/> plus a short random tail, not yet taken.</summary>
        public static string Unique(string basePath)
        {
            while (true)
            {
                string candidate = basePath + "-" + Guid.NewGuid().ToString("N").Substring(0, 8);
                if (!File.Exists(candidate) && !Directory.Exists(candidate)) return candidate;
            }
        }

        public static void DeleteDir(string dir, int patienceMs = 4000)
        {
            if (!Directory.Exists(dir)) return;
            foreach (var file in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
            {
                try
                {
                    var attrs = File.GetAttributes(file);
                    if ((attrs & (FileAttributes.ReadOnly | FileAttributes.Hidden | FileAttributes.System)) != 0)
                        File.SetAttributes(file, FileAttributes.Normal);
                }
                catch
                {
                    // the delete below will say
                }
            }
            Patient(() => Directory.Delete(dir, true), patienceMs);
        }

        public static bool TryDeleteDir(string dir, int patienceMs = 4000)
        {
            try
            {
                DeleteDir(dir, patienceMs);
                return true;
            }
            catch (Exception ex)
            {
                Log.Warn("could not remove " + dir + ": " + ex.Message);
                return false;
            }
        }

        public static bool TryDeleteFile(string path, int patienceMs = 2000)
        {
            try
            {
                if (!File.Exists(path)) return true;
                File.SetAttributes(path, FileAttributes.Normal);
                Patient(() => File.Delete(path), patienceMs);
                return true;
            }
            catch (Exception ex)
            {
                Log.Warn("could not remove " + path + ": " + ex.Message);
                return false;
            }
        }

        public static long DirSize(string dir)
        {
            long total = 0;
            try
            {
                foreach (var f in new DirectoryInfo(dir).EnumerateFiles("*", SearchOption.AllDirectories)) total += f.Length;
            }
            catch
            {
                // best effort: this only feeds the size shown in Settings
            }
            return total;
        }

        public static bool IsInside(string path, string root)
        {
            try
            {
                string full = Path.GetFullPath(path);
                string prefix = Path.GetFullPath(root).TrimEnd('\\') + "\\";
                return full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }
    }
}
