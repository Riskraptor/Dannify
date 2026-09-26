using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// The modern Windows folder picker (the one File Explorer uses), not the
    /// old tree view that .NET Framework offers.
    /// </summary>
    internal static class FolderPicker
    {
        [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
        private class FileOpenDialog
        {
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("42F85136-DB7E-439C-85F1-E4075D135FC8")]
        private interface IFileDialog
        {
            [PreserveSig] int Show(IntPtr parent);
            void SetFileTypes(uint count, IntPtr specs);
            void SetFileTypeIndex(uint index);
            void GetFileTypeIndex(out uint index);
            void Advise(IntPtr sink, out uint cookie);
            void Unadvise(uint cookie);
            void SetOptions(uint options);
            void GetOptions(out uint options);
            void SetDefaultFolder(IShellItem item);
            void SetFolder(IShellItem item);
            void GetFolder(out IShellItem item);
            void GetCurrentSelection(out IShellItem item);
            void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
            void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
            void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
            void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
            void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
            void GetResult(out IShellItem item);
            void AddPlace(IShellItem item, int place);
            void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string ext);
            void Close(int hr);
            void SetClientGuid(ref Guid guid);
            void ClearClientData();
            void SetFilter(IntPtr filter);
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
        private interface IShellItem
        {
            void BindToHandler(IntPtr bc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
            void GetParent(out IShellItem parent);
            void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
            void GetAttributes(uint mask, out uint attributes);
            void Compare(IShellItem other, uint hint, out int order);
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
        private static extern void SHCreateItemFromParsingName(string path, IntPtr bc, ref Guid riid, out IShellItem item);

        private const uint FOS_NOCHANGEDIR = 0x8;
        private const uint FOS_PICKFOLDERS = 0x20;
        private const uint FOS_FORCEFILESYSTEM = 0x40;
        private const uint FOS_PATHMUSTEXIST = 0x800;
        private const uint SIGDN_FILESYSPATH = 0x80058000;

        /// <summary>The chosen folder, or null if the user cancelled.</summary>
        public static string Pick(Window owner, string title, string start)
        {
            IFileDialog dialog = null;
            try
            {
                dialog = (IFileDialog)new FileOpenDialog();
                dialog.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR);
                dialog.SetTitle(title);
                string existing = start;
                while (!string.IsNullOrEmpty(existing) && !System.IO.Directory.Exists(existing))
                    existing = System.IO.Path.GetDirectoryName(existing);
                if (!string.IsNullOrEmpty(existing))
                {
                    var iid = typeof(IShellItem).GUID;
                    SHCreateItemFromParsingName(existing, IntPtr.Zero, ref iid, out IShellItem folder);
                    dialog.SetFolder(folder);
                }
                IntPtr hwnd = owner == null ? IntPtr.Zero : new WindowInteropHelper(owner).Handle;
                if (dialog.Show(hwnd) != 0) return null;
                dialog.GetResult(out IShellItem result);
                result.GetDisplayName(SIGDN_FILESYSPATH, out string path);
                return path;
            }
            catch
            {
                return null;
            }
            finally
            {
                if (dialog != null) Marshal.FinalReleaseComObject(dialog);
            }
        }
    }
}
