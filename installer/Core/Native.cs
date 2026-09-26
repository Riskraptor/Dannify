using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Dannify.Setup.Core
{
    internal static class Native
    {
        public const uint PROCESS_TERMINATE = 0x0001;
        public const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        public const uint SYNCHRONIZE = 0x00100000;
        public const uint EVENT_MODIFY_STATE = 0x0002;
        public const uint WAIT_OBJECT_0 = 0;
        public const uint WAIT_TIMEOUT = 0x102;
        public const int ASFW_ANY = -1;

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool QueryFullProcessImageNameW(IntPtr process, int flags, StringBuilder name, ref int size);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool CloseHandle(IntPtr handle);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool TerminateProcess(IntPtr process, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern IntPtr OpenMutexW(uint access, bool inherit, string name);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern IntPtr CreateMutexW(IntPtr attributes, bool initialOwner, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool ReleaseMutex(IntPtr mutex);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern IntPtr OpenEventW(uint access, bool inherit, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool SetEvent(IntPtr handle);

        [StructLayout(LayoutKind.Sequential)]
        public struct MEMORYSTATUSEX
        {
            public uint dwLength;
            public uint dwMemoryLoad;
            public ulong ullTotalPhys;
            public ulong ullAvailPhys;
            public ulong ullTotalPageFile;
            public ulong ullAvailPageFile;
            public ulong ullTotalVirtual;
            public ulong ullAvailVirtual;
            public ulong ullAvailExtendedVirtual;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX status);

        public static ulong AvailableMemory()
        {
            try
            {
                var status = new MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX)) };
                if (GlobalMemoryStatusEx(ref status)) return status.ullAvailPhys;
            }
            catch
            {
                // fall through
            }
            return 0;
        }

        [DllImport("user32.dll")]
        public static extern bool AllowSetForegroundWindow(int pid);

        public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out int pid);

        [DllImport("user32.dll")]
        public static extern bool IsWindowVisible(IntPtr hwnd);

        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        public static extern IntPtr GetWindow(IntPtr hwnd, uint cmd);

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left, Top, Right, Bottom;
        }

        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);

        [DllImport("shell32.dll")]
        public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);

        public const int SHCNE_ASSOCCHANGED = 0x08000000;

        [DllImport("dwmapi.dll")]
        public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        public const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
        public const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        public const int DWMWA_BORDER_COLOR = 34;
        public const int DWMWCP_ROUND = 2;

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        public static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
    }
}
