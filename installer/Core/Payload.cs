using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using FileOps = Dannify.Setup.Core.Files; // `Files` here is the payload's own list

namespace Dannify.Setup.Core
{
    internal sealed class PayloadFile
    {
        public string Path;     // relative, backslashes
        public long Size;
        public string Sha256;   // lowercase hex
        public long Offset;     // where it starts in the unpacked stream
    }

    internal sealed class PayloadBlock
    {
        public long PackedOffset; // from the first block
        public int PackedSize;
        public long Start;        // in the unpacked stream
        public int Size;
    }

    /// <summary>
    /// The app, packed onto the end of the installer.
    ///
    ///   [this program][payload][trailer: "DNFYPAK1", offset, length, sha256]
    ///   payload = [u32 header length][header text][LZMA block][LZMA block]...
    ///
    /// Every file sits back to back in one unpacked stream, which is cut into
    /// fixed-size blocks that were compressed independently. Blocks do not
    /// line up with files, so a big file spans several of them and a block
    /// can end in the middle of one; each block is written wherever its bytes
    /// belong. See packaging/make_setup.py for the writing side.
    /// </summary>
    internal sealed class Payload
    {
        private static readonly byte[] Magic = Encoding.ASCII.GetBytes("DNFYPAK1");
        public const int TrailerSize = 8 + 8 + 8 + 32;

        public string SourcePath { get; private set; }
        public long Offset { get; private set; }
        public long Length { get; private set; }
        public byte[] Checksum { get; private set; }
        public string Version { get; private set; }
        public long TotalSize { get; private set; }
        public IReadOnlyList<PayloadFile> Files => _files;
        public IReadOnlyList<PayloadBlock> Blocks => _blocks;

        private int _lc, _lp, _pb;
        private uint _dict;
        private long _dataStart;
        private readonly List<PayloadFile> _files = new List<PayloadFile>();
        private readonly List<PayloadBlock> _blocks = new List<PayloadBlock>();

        /// <summary>The payload on the end of <paramref name="exe"/>, or null when there is none.</summary>
        public static Payload Open(string exe)
        {
            try
            {
                using (var fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                {
                    // A code-signed setup has its signature appended after the
                    // trailer, so the trailer ends where the signature starts.
                    long end = TrailerEnd(fs, SignedEnd(fs));
                    if (end < TrailerSize + 16) return null;
                    fs.Seek(end - TrailerSize, SeekOrigin.Begin);
                    var trailer = ReadExactly(fs, TrailerSize);
                    for (int i = 0; i < Magic.Length; i++)
                        if (trailer[i] != Magic[i]) return null;
                    long offset = BitConverter.ToInt64(trailer, 8);
                    long length = BitConverter.ToInt64(trailer, 16);
                    if (offset <= 0 || length <= 0 || offset + length != end - TrailerSize)
                        throw new InvalidDataException("payload trailer does not match the file");
                    var payload = new Payload
                    {
                        SourcePath = exe,
                        Offset = offset,
                        Length = length,
                        Checksum = trailer.Skip(24).Take(32).ToArray(),
                    };
                    payload.ReadHeader(fs);
                    return payload;
                }
            }
            catch (InvalidDataException)
            {
                throw;
            }
            catch (Exception ex)
            {
                Log.Warn("no readable payload: " + ex.Message);
                return null;
            }
        }

        /// <summary>
        /// Where the file's own content ends: its length, less an Authenticode
        /// signature when one sits at the very end (where Windows puts it). The
        /// PE header's security directory says where that is, as a file offset.
        /// Anything that does not read as exactly that is left alone, and the
        /// whole length counts, as it did before setups were signed.
        /// </summary>
        internal static long SignedEnd(Stream fs)
        {
            long length = fs.Length;
            try
            {
                if (length < 0x40) return length;
                fs.Seek(0, SeekOrigin.Begin);
                var dos = ReadExactly(fs, 0x40);
                if (dos[0] != (byte)'M' || dos[1] != (byte)'Z') return length;
                long pe = BitConverter.ToInt32(dos, 0x3C);
                if (pe <= 0 || pe + 24 + 2 > length) return length;
                fs.Seek(pe, SeekOrigin.Begin);
                var head = ReadExactly(fs, 24 + 2);
                if (head[0] != (byte)'P' || head[1] != (byte)'E' || head[2] != 0 || head[3] != 0) return length;
                ushort magic = BitConverter.ToUInt16(head, 24);
                long dirs = pe + 24 + (magic == 0x20b ? 112 : magic == 0x10b ? 96 : -1);
                if (dirs < pe + 24) return length;
                long security = dirs + 4 * 8; // IMAGE_DIRECTORY_ENTRY_SECURITY
                if (security + 8 > length) return length;
                fs.Seek(security, SeekOrigin.Begin);
                var entry = ReadExactly(fs, 8);
                long at = BitConverter.ToUInt32(entry, 0);
                long size = BitConverter.ToUInt32(entry, 4);
                if (at <= 0 || size <= 0 || at + size != length) return length;
                return at;
            }
            catch (Exception)
            {
                return length;
            }
        }

        /// <summary>
        /// Signing first pads the file with zeros to a multiple of 8 bytes, so
        /// the trailer can end up to 7 bytes before <paramref name="end"/>.
        /// Only zero bytes are stepped over, and only to land on the magic.
        /// </summary>
        private static long TrailerEnd(Stream fs, long end)
        {
            if (end == fs.Length || end < TrailerSize + 8) return end;
            fs.Seek(end - TrailerSize - 7, SeekOrigin.Begin);
            var tail = ReadExactly(fs, TrailerSize + 7);
            for (int pad = 0; pad <= 7; pad++)
            {
                if (pad > 0 && tail[tail.Length - pad] != 0) break;
                int start = tail.Length - pad - TrailerSize;
                bool match = true;
                for (int i = 0; i < Magic.Length && match; i++) match = tail[start + i] == Magic[i];
                if (match) return end - pad;
            }
            return end;
        }

        private static byte[] ReadExactly(Stream s, int count)
        {
            var buf = new byte[count];
            int got = 0;
            while (got < count)
            {
                int n = s.Read(buf, got, count - got);
                if (n <= 0) throw new InvalidDataException("unexpected end of file");
                got += n;
            }
            return buf;
        }

        private void ReadHeader(FileStream fs)
        {
            fs.Seek(Offset, SeekOrigin.Begin);
            int headerLength = BitConverter.ToInt32(ReadExactly(fs, 4), 0);
            if (headerLength <= 0 || headerLength > 4 * 1024 * 1024 || headerLength > Length)
                throw new InvalidDataException("bad payload header size");
            string text = Encoding.UTF8.GetString(ReadExactly(fs, headerLength));
            _dataStart = Offset + 4 + headerLength;

            var lines = text.Split('\n');
            if (lines.Length < 3 || lines[0].Trim() != "DPK1") throw new InvalidDataException("unknown payload format");
            long packedAt = 0, unpackedAt = 0, fileAt = 0;
            bool ended = false;
            foreach (var raw in lines.Skip(1))
            {
                string line = raw.TrimEnd('\r');
                if (line.Length == 0) continue;
                int eq = line.IndexOf('=');
                string key = eq < 0 ? line : line.Substring(0, eq);
                string value = eq < 0 ? "" : line.Substring(eq + 1);
                switch (key)
                {
                    case "version":
                        Version = value;
                        break;
                    case "lzma":
                    {
                        var p = value.Split(',');
                        _lc = int.Parse(p[0], CultureInfo.InvariantCulture);
                        _lp = int.Parse(p[1], CultureInfo.InvariantCulture);
                        _pb = int.Parse(p[2], CultureInfo.InvariantCulture);
                        _dict = uint.Parse(p[3], CultureInfo.InvariantCulture);
                        break;
                    }
                    case "total":
                        TotalSize = long.Parse(value, CultureInfo.InvariantCulture);
                        break;
                    case "block":
                    {
                        var p = value.Split(',');
                        var block = new PayloadBlock
                        {
                            PackedSize = int.Parse(p[0], CultureInfo.InvariantCulture),
                            Size = int.Parse(p[1], CultureInfo.InvariantCulture),
                            PackedOffset = packedAt,
                            Start = unpackedAt,
                        };
                        if (block.PackedSize <= 0 || block.Size <= 0) throw new InvalidDataException("bad block");
                        packedAt += block.PackedSize;
                        unpackedAt += block.Size;
                        _blocks.Add(block);
                        break;
                    }
                    case "file":
                    {
                        // size,sha256,path: the path goes last because it may hold commas.
                        int a = value.IndexOf(',');
                        int b = value.IndexOf(',', a + 1);
                        if (a < 0 || b < 0) throw new InvalidDataException("bad file entry");
                        var file = new PayloadFile
                        {
                            Size = long.Parse(value.Substring(0, a), CultureInfo.InvariantCulture),
                            Sha256 = value.Substring(a + 1, b - a - 1).ToLowerInvariant(),
                            Path = CheckedPath(value.Substring(b + 1)),
                            Offset = fileAt,
                        };
                        if (file.Size < 0 || file.Sha256.Length != 64) throw new InvalidDataException("bad file entry");
                        fileAt += file.Size;
                        _files.Add(file);
                        break;
                    }
                    case "end":
                        ended = true;
                        break;
                }
            }
            if (!ended || string.IsNullOrEmpty(Version) || _files.Count == 0 || _blocks.Count == 0)
                throw new InvalidDataException("incomplete payload header");
            if (fileAt != TotalSize || unpackedAt != TotalSize)
                throw new InvalidDataException("payload sizes do not add up");
            if (_dataStart + packedAt != Offset + Length)
                throw new InvalidDataException("payload blocks do not fill the payload");
        }

        /// <summary>
        /// A path from the payload, refused unless it stays inside the folder
        /// it is written to. It came out of a file, so it is not trusted.
        /// </summary>
        private static string CheckedPath(string rel)
        {
            if (string.IsNullOrWhiteSpace(rel) || rel != rel.Trim()) throw new InvalidDataException("bad path");
            if (rel.StartsWith("/") || rel.StartsWith("\\") || rel.Contains(":")) throw new InvalidDataException("bad path");
            var parts = rel.Replace('\\', '/').Split('/');
            if (parts.Any(p => p.Length == 0 || p == "." || p == ".."))
                throw new InvalidDataException("bad path");
            if (rel.IndexOfAny(System.IO.Path.GetInvalidPathChars()) >= 0) throw new InvalidDataException("bad path");
            return string.Join("\\", parts);
        }

        /// <summary>Check the whole payload against the checksum in the trailer.</summary>
        public void VerifyChecksum(CancellationToken ct, Action<double> progress = null)
        {
            using (var sha = SHA256.Create())
            using (var fs = new FileStream(SourcePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 16))
            {
                fs.Seek(Offset, SeekOrigin.Begin);
                var buf = new byte[1 << 20];
                long left = Length;
                while (left > 0)
                {
                    ct.ThrowIfCancellationRequested();
                    int n = fs.Read(buf, 0, (int)Math.Min(buf.Length, left));
                    if (n <= 0) throw new InvalidDataException("payload is shorter than it says");
                    sha.TransformBlock(buf, 0, n, null, 0);
                    left -= n;
                    progress?.Invoke(1.0 - (double)left / Length);
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                if (!sha.Hash.SequenceEqual(Checksum)) throw new InvalidDataException("payload checksum does not match");
            }
        }

        /// <summary>
        /// Unpack every file under <paramref name="target"/>, which must not
        /// exist yet or be empty. <paramref name="onBytes"/> is told how many
        /// more bytes came out, from whichever thread did the work.
        /// </summary>
        public void Extract(string target, CancellationToken ct, Action<long> onBytes)
        {
            Directory.CreateDirectory(target);

            // Every file exists at its final size before any block is written,
            // so blocks can land in any order.
            foreach (var file in _files)
            {
                ct.ThrowIfCancellationRequested();
                string path = System.IO.Path.Combine(target, file.Path);
                Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
                using (var fs = FileOps.Open(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite))
                    fs.SetLength(file.Size);
            }

            int threads = Math.Max(1, Math.Min(Math.Min(Environment.ProcessorCount, 4), _blocks.Count));
            ulong free = Native.AvailableMemory();
            if (free != 0 && free < 1024UL * 1024 * 1024) threads = Math.Min(threads, 2);

            var options = new ParallelOptions { MaxDegreeOfParallelism = threads, CancellationToken = ct };
            var buffers = new ThreadLocal<byte[]>(() => null);
            try
            {
                Parallel.ForEach(_blocks, options, block =>
                {
                    byte[] packed;
                    using (var fs = new FileStream(SourcePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 16))
                    {
                        fs.Seek(_dataStart + block.PackedOffset, SeekOrigin.Begin);
                        packed = ReadExactly(fs, block.PackedSize);
                    }
                    var output = buffers.Value;
                    if (output == null || output.Length < block.Size)
                        buffers.Value = output = new byte[block.Size];

                    int reported = 0;
                    var decoder = new LzmaDecoder(_lc, _lp, _pb, _dict);
                    decoder.Decode(packed, 0, packed.Length, output, block.Size, done =>
                    {
                        ct.ThrowIfCancellationRequested();
                        onBytes?.Invoke(done - reported);
                        reported = done;
                    });
                    WriteBlock(target, block, output);
                });
            }
            finally
            {
                buffers.Dispose();
            }
        }

        private void WriteBlock(string target, PayloadBlock block, byte[] data)
        {
            long blockEnd = block.Start + block.Size;
            // Files are in stream order: find the first one that reaches into this block.
            int lo = 0, hi = _files.Count - 1, first = _files.Count;
            while (lo <= hi)
            {
                int mid = (lo + hi) / 2;
                if (_files[mid].Offset + _files[mid].Size > block.Start)
                {
                    first = mid;
                    hi = mid - 1;
                }
                else
                {
                    lo = mid + 1;
                }
            }
            for (int i = first; i < _files.Count; i++)
            {
                var file = _files[i];
                if (file.Offset >= blockEnd) break;
                if (file.Size == 0) continue;
                long from = Math.Max(file.Offset, block.Start);
                long to = Math.Min(file.Offset + file.Size, blockEnd);
                if (to <= from) continue;
                string path = System.IO.Path.Combine(target, file.Path);
                using (var fs = FileOps.Open(path, FileMode.Open, FileAccess.Write, FileShare.ReadWrite, 1 << 16))
                {
                    fs.Seek(from - file.Offset, SeekOrigin.Begin);
                    fs.Write(data, (int)(from - block.Start), (int)(to - from));
                }
            }
        }

        /// <summary>
        /// Hash every unpacked file against the payload's list. Throws on the
        /// first one that does not match.
        /// </summary>
        public void VerifyFiles(string target, CancellationToken ct, Action<long> onBytes)
        {
            int threads = Math.Max(1, Math.Min(Environment.ProcessorCount, 4));
            var options = new ParallelOptions { MaxDegreeOfParallelism = threads, CancellationToken = ct };
            Parallel.ForEach(_files.OrderByDescending(f => f.Size), options, file =>
            {
                string path = System.IO.Path.Combine(target, file.Path);
                string actual = HashFile(path, ct, onBytes);
                if (actual != file.Sha256)
                    throw new InvalidDataException("file does not match: " + file.Path);
            });
        }

        public static string HashFile(string path, CancellationToken ct, Action<long> onBytes = null)
        {
            using (var sha = SHA256.Create())
            using (var fs = FileOps.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete, 1 << 16))
            {
                var buf = new byte[1 << 20];
                int n;
                while ((n = fs.Read(buf, 0, buf.Length)) > 0)
                {
                    ct.ThrowIfCancellationRequested();
                    sha.TransformBlock(buf, 0, n, null, 0);
                    onBytes?.Invoke(n);
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                var sb = new StringBuilder(64);
                foreach (byte b in sha.Hash) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return sb.ToString();
            }
        }

        /// <summary>
        /// Write this program, without the payload, to <paramref name="dest"/>:
        /// that copy is the launcher and uninstaller that stays installed.
        /// </summary>
        public void WriteEngine(string dest)
        {
            using (var src = new FileStream(SourcePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var dst = FileOps.Open(dest, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                var buf = new byte[1 << 16];
                long left = Offset;
                long written = 0;
                // A signed setup's header points at a signature on the end of
                // the setup, which the launcher copy does not have, and carries
                // the checksum signing wrote. Both are put back to the zeros the
                // engine was built with, so the copy is that engine, byte for
                // byte: a plain program that does not claim a signature.
                long[] blank = SignedHeaderFields(src);
                while (left > 0)
                {
                    int n = src.Read(buf, 0, (int)Math.Min(buf.Length, left));
                    if (n <= 0) throw new InvalidDataException("setup file is shorter than it says");
                    for (int f = 0; f + 1 < blank.Length; f += 2)
                    {
                        long from = Math.Max(blank[f], written), to = Math.Min(blank[f] + blank[f + 1], written + n);
                        for (long i = from; i < to; i++) buf[i - written] = 0;
                    }
                    dst.Write(buf, 0, n);
                    written += n;
                    left -= n;
                }
            }
        }

        /// <summary>
        /// (offset, length) pairs of the PE header fields signing changes: the
        /// checksum and the security directory entry. Empty when the file does
        /// not carry a signature, so an unsigned setup is copied untouched.
        /// </summary>
        private static long[] SignedHeaderFields(Stream fs)
        {
            long at = fs.Position;
            try
            {
                if (SignedEnd(fs) == fs.Length) return new long[0];
                fs.Seek(0, SeekOrigin.Begin);
                var dos = ReadExactly(fs, 0x40);
                long pe = BitConverter.ToInt32(dos, 0x3C);
                fs.Seek(pe, SeekOrigin.Begin);
                var head = ReadExactly(fs, 26);
                ushort magic = BitConverter.ToUInt16(head, 24);
                long optional = pe + 24;
                long security = optional + (magic == 0x20b ? 112 : 96) + 4 * 8;
                return new long[] { optional + 64, 4, security, 8 };
            }
            catch (Exception)
            {
                return new long[0];
            }
            finally
            {
                fs.Seek(at, SeekOrigin.Begin);
            }
        }
    }
}
