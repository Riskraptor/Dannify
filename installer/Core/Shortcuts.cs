using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// Start menu and desktop shortcuts, carrying Dannify's app identity.
    ///
    /// The identity (System.AppUserModel.ID) has to match what the app claims
    /// for itself (APP_USER_MODEL_ID in desktop.py). That is what lets Windows
    /// treat the running window and the shortcut as one app: the taskbar
    /// button pins as the shortcut, and the media flyout knows its name.
    /// </summary>
    internal static class Shortcuts
    {
        [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
        private class ShellLink
        {
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
        private interface IShellLinkW
        {
            void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int cch, IntPtr findData, uint flags);
            void GetIDList(out IntPtr pidl);
            void SetIDList(IntPtr pidl);
            void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int cch);
            void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
            void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int cch);
            void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
            void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int cch);
            void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
            void GetHotkey(out short hotkey);
            void SetHotkey(short hotkey);
            void GetShowCmd(out int showCmd);
            void SetShowCmd(int showCmd);
            void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int cch, out int index);
            void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
            void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
            void Resolve(IntPtr hwnd, uint flags);
            void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        private struct PropertyKey
        {
            public Guid FormatId;
            public uint PropertyId;
        }

        // PROPVARIANT is 24 bytes on 64-bit Windows; only vt and the string
        // pointer are used, the rest is there so nothing reads past the end.
        [StructLayout(LayoutKind.Explicit, Size = 24)]
        private struct PropVariant
        {
            [FieldOffset(0)] public ushort vt;
            [FieldOffset(8)] public IntPtr pointer;
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
        private interface IPropertyStore
        {
            void GetCount(out uint count);
            void GetAt(uint index, out PropertyKey key);
            void GetValue(ref PropertyKey key, out PropVariant value);
            void SetValue(ref PropertyKey key, ref PropVariant value);
            void Commit();
        }

        private const ushort VT_LPWSTR = 31;
        private static readonly Guid AppUserModelFormat = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");

        public static void Create(string lnkPath, string target, string workingDir, string description, string appId)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(lnkPath));
            var link = (IShellLinkW)new ShellLink();
            try
            {
                link.SetPath(target);
                link.SetWorkingDirectory(workingDir);
                link.SetDescription(description);
                link.SetIconLocation(target, 0);

                if (!string.IsNullOrEmpty(appId))
                {
                    var store = (IPropertyStore)link;
                    var key = new PropertyKey { FormatId = AppUserModelFormat, PropertyId = 5 };
                    var value = new PropVariant { vt = VT_LPWSTR, pointer = Marshal.StringToCoTaskMemUni(appId) };
                    try
                    {
                        store.SetValue(ref key, ref value);
                        store.Commit();
                    }
                    finally
                    {
                        Marshal.FreeCoTaskMem(value.pointer);
                    }
                }

                // Written beside the final name and moved over it, so an
                // existing (pinned) shortcut is replaced in one step.
                string temp = lnkPath + ".tmp.lnk";
                ((IPersistFile)link).Save(temp, true);
                if (File.Exists(lnkPath)) File.Delete(lnkPath);
                File.Move(temp, lnkPath);
            }
            finally
            {
                Marshal.FinalReleaseComObject(link);
            }
        }

        /// <summary>Where a shortcut points, or null if it cannot be read.</summary>
        public static string TargetOf(string lnkPath)
        {
            if (!File.Exists(lnkPath)) return null;
            object link = null;
            try
            {
                link = new ShellLink();
                ((IPersistFile)link).Load(lnkPath, 0);
                var sb = new StringBuilder(1024);
                ((IShellLinkW)link).GetPath(sb, sb.Capacity, IntPtr.Zero, 0x4 /* SLGP_RAWPATH */);
                return Environment.ExpandEnvironmentVariables(sb.ToString());
            }
            catch
            {
                return null;
            }
            finally
            {
                if (link != null) Marshal.FinalReleaseComObject(link);
            }
        }

        /// <summary>Whether a shortcut points into <paramref name="root"/>.</summary>
        public static bool PointsInto(string lnkPath, string root)
        {
            string target = TargetOf(lnkPath);
            if (string.IsNullOrEmpty(target)) return false;
            try
            {
                string full = Path.GetFullPath(target);
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
