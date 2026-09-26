using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// A small rolling log in the data folder, for working out what happened
    /// after the fact. Nothing in it is ever shown to anyone.
    /// </summary>
    internal static class Log
    {
        private static readonly object Gate = new object();
        private static string _path;
        private static readonly int Pid = Process.GetCurrentProcess().Id;

        public static void Init(string dataDir)
        {
            try
            {
                if (string.IsNullOrEmpty(dataDir)) return;
                _path = Path.Combine(dataDir, "setup.log");
            }
            catch
            {
                _path = null;
            }
        }

        public static void Info(string message) => Write("INFO ", message);
        public static void Warn(string message) => Write("WARN ", message);

        public static void Error(string message, Exception ex = null) =>
            Write("ERROR", ex == null ? message : message + " | " + ex.GetType().Name + ": " + ex.Message +
                (ex.InnerException == null ? "" : " <- " + ex.InnerException.Message));

        private static void Write(string level, string message)
        {
            lock (Gate)
            {
                try
                {
                    if (_path == null) return;
                    Directory.CreateDirectory(Path.GetDirectoryName(_path));
                    var info = new FileInfo(_path);
                    if (info.Exists && info.Length > 512 * 1024)
                    {
                        string old = _path + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(_path, old);
                    }
                    File.AppendAllText(_path, string.Format(CultureInfo.InvariantCulture,
                        "{0:yyyy-MM-dd HH:mm:ss.fff} {1} [{2}] {3}\r\n", DateTime.Now, level, Pid, message));
                }
                catch
                {
                    // A log that cannot be written is not worth failing over.
                }
            }
        }
    }
}
