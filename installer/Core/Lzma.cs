using System;
using System.IO;
using System.Runtime.CompilerServices;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// An LZMA decoder for one raw block, written after the reference decoder
    /// in the public domain LZMA SDK (LzmaSpec.cpp, Igor Pavlov).
    ///
    /// The installer's payload is split into blocks that were each compressed
    /// on their own, so every block starts from a fresh model and can be
    /// decoded on its own thread. A block is decoded straight into a buffer of
    /// exactly its unpacked size, which doubles as the dictionary: nothing
    /// ever wraps, and a match can only point backwards into bytes already
    /// written.
    ///
    /// Anything that does not add up (a distance past the start, a stream
    /// that ends early or runs long, input read past its end) throws, and the
    /// caller also checks every file's SHA-256 afterwards.
    /// </summary>
    internal sealed class LzmaDecoder
    {
        private const int NumBitModelTotalBits = 11;
        private const uint BitModelTotal = 1u << NumBitModelTotalBits;
        private const int NumMoveBits = 5;
        private const uint TopValue = 1u << 24;
        private const int NumPosBitsMax = 4;
        private const int NumStates = 12;
        private const int NumLenToPosStates = 4;
        private const int NumAlignBits = 4;
        private const int EndPosModelIndex = 14;
        private const int NumFullDistances = 1 << (EndPosModelIndex >> 1);
        private const int MatchMinLen = 2;

        private readonly int _lc;
        private readonly int _lp;
        private readonly int _pb;
        private readonly uint _dictSize;

        private byte[] _in;
        private int _inPos;
        private int _inEnd;
        private bool _inputOverrun;

        private uint _range;
        private uint _code;

        private byte[] _out;
        private int _outPos;
        private int _outLimit;

        private readonly ushort[] _literal;
        private readonly ushort[] _posSlot = new ushort[NumLenToPosStates << 6];
        private readonly ushort[] _posDecoders = new ushort[1 + NumFullDistances - EndPosModelIndex];
        private readonly ushort[] _align = new ushort[1 << NumAlignBits];
        private readonly ushort[] _isMatch = new ushort[NumStates << NumPosBitsMax];
        private readonly ushort[] _isRep = new ushort[NumStates];
        private readonly ushort[] _isRepG0 = new ushort[NumStates];
        private readonly ushort[] _isRepG1 = new ushort[NumStates];
        private readonly ushort[] _isRepG2 = new ushort[NumStates];
        private readonly ushort[] _isRep0Long = new ushort[NumStates << NumPosBitsMax];

        private readonly ushort[] _lenChoice = new ushort[2];
        private readonly ushort[] _lenLow = new ushort[(1 << NumPosBitsMax) << 3];
        private readonly ushort[] _lenMid = new ushort[(1 << NumPosBitsMax) << 3];
        private readonly ushort[] _lenHigh = new ushort[256];
        private readonly ushort[] _repChoice = new ushort[2];
        private readonly ushort[] _repLow = new ushort[(1 << NumPosBitsMax) << 3];
        private readonly ushort[] _repMid = new ushort[(1 << NumPosBitsMax) << 3];
        private readonly ushort[] _repHigh = new ushort[256];

        public LzmaDecoder(int lc, int lp, int pb, uint dictSize)
        {
            if (lc < 0 || lc > 8 || lp < 0 || lp > 4 || pb < 0 || pb > 4)
                throw new InvalidDataException("bad LZMA properties");
            _lc = lc;
            _lp = lp;
            _pb = pb;
            _dictSize = Math.Max(dictSize, 1u << 12);
            _literal = new ushort[0x300 << (lc + lp)];
        }

        /// <summary>
        /// Decode <paramref name="input"/>[<paramref name="inOffset"/>, +<paramref name="inCount"/>)
        /// into <paramref name="output"/>[0, <paramref name="outCount"/>).
        /// <paramref name="onProgress"/> gets the running total of bytes out,
        /// roughly every megabyte.
        /// </summary>
        public void Decode(byte[] input, int inOffset, int inCount, byte[] output, int outCount,
            Action<int> onProgress = null)
        {
            if (outCount > output.Length) throw new ArgumentException("output too small");
            _in = input;
            _inPos = inOffset;
            _inEnd = inOffset + inCount;
            _inputOverrun = false;
            _out = output;
            _outPos = 0;
            _outLimit = outCount;
            Reset();
            InitRange();

            uint rep0 = 0, rep1 = 0, rep2 = 0, rep3 = 0;
            int state = 0;
            int pbMask = (1 << _pb) - 1;
            int nextReport = 1 << 20;

            while (true)
            {
                if (_outPos >= nextReport)
                {
                    onProgress?.Invoke(_outPos);
                    nextReport = _outPos + (1 << 20);
                }

                if (_outPos == _outLimit && _code == 0)
                    break; // everything is out and the coder finished cleanly: no end marker

                int posState = _outPos & pbMask;
                if (Bit(_isMatch, (state << NumPosBitsMax) + posState) == 0)
                {
                    if (_outPos == _outLimit) throw Corrupt("data past the end");
                    Literal(state, rep0);
                    state = state < 4 ? 0 : (state < 10 ? state - 3 : state - 6);
                    continue;
                }

                uint len;
                if (Bit(_isRep, state) != 0)
                {
                    if (_outPos == _outLimit || _outPos == 0) throw Corrupt("bad repeat");
                    if (Bit(_isRepG0, state) == 0)
                    {
                        if (Bit(_isRep0Long, (state << NumPosBitsMax) + posState) == 0)
                        {
                            // Short repeat: one byte from rep0 back.
                            if (rep0 >= (uint)_outPos) throw Corrupt("distance");
                            state = state < 7 ? 9 : 11;
                            _out[_outPos] = _out[_outPos - (int)rep0 - 1];
                            _outPos++;
                            continue;
                        }
                    }
                    else
                    {
                        uint dist;
                        if (Bit(_isRepG1, state) == 0)
                        {
                            dist = rep1;
                        }
                        else
                        {
                            if (Bit(_isRepG2, state) == 0)
                            {
                                dist = rep2;
                            }
                            else
                            {
                                dist = rep3;
                                rep3 = rep2;
                            }
                            rep2 = rep1;
                        }
                        rep1 = rep0;
                        rep0 = dist;
                    }
                    len = Length(_repChoice, _repLow, _repMid, _repHigh, posState);
                    state = state < 7 ? 8 : 11;
                }
                else
                {
                    rep3 = rep2;
                    rep2 = rep1;
                    rep1 = rep0;
                    len = Length(_lenChoice, _lenLow, _lenMid, _lenHigh, posState);
                    state = state < 7 ? 7 : 10;
                    rep0 = Distance(len);
                    if (rep0 == 0xFFFFFFFF)
                    {
                        // End marker. Only acceptable exactly at the end.
                        if (_outPos == _outLimit && _code == 0) break;
                        throw Corrupt("early end");
                    }
                    if (_outPos == _outLimit) throw Corrupt("data past the end");
                    if (rep0 >= _dictSize || rep0 >= (uint)_outPos) throw Corrupt("distance");
                }

                len += MatchMinLen;
                if ((uint)(_outLimit - _outPos) < len) throw Corrupt("match past the end");
                if (rep0 >= (uint)_outPos) throw Corrupt("distance");
                int src = _outPos - (int)rep0 - 1;
                int n = (int)len;
                if (rep0 + 1 >= len)
                {
                    // No overlap: a straight block copy.
                    Buffer.BlockCopy(_out, src, _out, _outPos, n);
                    _outPos += n;
                }
                else
                {
                    for (int i = 0; i < n; i++) _out[_outPos++] = _out[src++];
                }
            }

            if (_inputOverrun) throw Corrupt("input ran out");
            onProgress?.Invoke(_outPos);
        }

        private static InvalidDataException Corrupt(string what) =>
            new InvalidDataException("damaged data (" + what + ")");

        private void Reset()
        {
            Fill(_literal);
            Fill(_posSlot);
            Fill(_posDecoders);
            Fill(_align);
            Fill(_isMatch);
            Fill(_isRep);
            Fill(_isRepG0);
            Fill(_isRepG1);
            Fill(_isRepG2);
            Fill(_isRep0Long);
            Fill(_lenChoice);
            Fill(_lenLow);
            Fill(_lenMid);
            Fill(_lenHigh);
            Fill(_repChoice);
            Fill(_repLow);
            Fill(_repMid);
            Fill(_repHigh);
        }

        private static void Fill(ushort[] probs)
        {
            for (int i = 0; i < probs.Length; i++) probs[i] = (ushort)(BitModelTotal >> 1);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private uint NextByte()
        {
            if (_inPos < _inEnd) return _in[_inPos++];
            _inputOverrun = true;
            return 0;
        }

        private void InitRange()
        {
            _range = 0xFFFFFFFF;
            _code = 0;
            uint first = NextByte();
            for (int i = 0; i < 4; i++) _code = (_code << 8) | NextByte();
            if (first != 0 || _code == _range) throw Corrupt("header");
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private uint Bit(ushort[] probs, int index)
        {
            uint v = probs[index];
            uint bound = (_range >> NumBitModelTotalBits) * v;
            uint symbol;
            if (_code < bound)
            {
                v += (BitModelTotal - v) >> NumMoveBits;
                _range = bound;
                symbol = 0;
            }
            else
            {
                v -= v >> NumMoveBits;
                _code -= bound;
                _range -= bound;
                symbol = 1;
            }
            probs[index] = (ushort)v;
            if (_range < TopValue)
            {
                _range <<= 8;
                _code = (_code << 8) | NextByte();
            }
            return symbol;
        }

        private uint DirectBits(int numBits)
        {
            uint res = 0;
            do
            {
                _range >>= 1;
                _code -= _range;
                uint t = 0u - (_code >> 31);
                _code += _range & t;
                if (_code == _range) throw Corrupt("direct bits");
                if (_range < TopValue)
                {
                    _range <<= 8;
                    _code = (_code << 8) | NextByte();
                }
                res <<= 1;
                res += t + 1;
            } while (--numBits > 0);
            return res;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private uint Tree(ushort[] probs, int offset, int numBits)
        {
            uint m = 1;
            for (int i = 0; i < numBits; i++) m = (m << 1) + Bit(probs, offset + (int)m);
            return m - (1u << numBits);
        }

        private uint ReverseTree(ushort[] probs, int offset, int numBits)
        {
            uint m = 1, symbol = 0;
            for (int i = 0; i < numBits; i++)
            {
                uint bit = Bit(probs, offset + (int)m);
                m <<= 1;
                m += bit;
                symbol |= bit << i;
            }
            return symbol;
        }

        private uint Length(ushort[] choice, ushort[] low, ushort[] mid, ushort[] high, int posState)
        {
            if (Bit(choice, 0) == 0) return Tree(low, posState << 3, 3);
            if (Bit(choice, 1) == 0) return 8 + Tree(mid, posState << 3, 3);
            return 16 + Tree(high, 0, 8);
        }

        private uint Distance(uint len)
        {
            uint lenState = len > NumLenToPosStates - 1 ? NumLenToPosStates - 1 : len;
            uint slot = Tree(_posSlot, (int)(lenState << 6), 6);
            if (slot < 4) return slot;
            int numDirectBits = (int)((slot >> 1) - 1);
            uint dist = (2 | (slot & 1)) << numDirectBits;
            if (slot < EndPosModelIndex)
            {
                dist += ReverseTree(_posDecoders, (int)(dist - slot), numDirectBits);
            }
            else
            {
                dist += DirectBits(numDirectBits - NumAlignBits) << NumAlignBits;
                dist += ReverseTree(_align, 0, NumAlignBits);
            }
            return dist;
        }

        private void Literal(int state, uint rep0)
        {
            uint prevByte = _outPos > 0 ? _out[_outPos - 1] : 0u;
            uint symbol = 1;
            int litState = ((_outPos & ((1 << _lp) - 1)) << _lc) + (int)(prevByte >> (8 - _lc));
            int probs = 0x300 * litState;
            if (state >= 7)
            {
                if (rep0 >= (uint)_outPos) throw Corrupt("distance");
                uint matchByte = _out[_outPos - (int)rep0 - 1];
                do
                {
                    uint matchBit = (matchByte >> 7) & 1;
                    matchByte <<= 1;
                    uint bit = Bit(_literal, probs + (int)(((1 + matchBit) << 8) + symbol));
                    symbol = (symbol << 1) | bit;
                    if (matchBit != bit) break;
                } while (symbol < 0x100);
            }
            while (symbol < 0x100) symbol = (symbol << 1) | Bit(_literal, probs + (int)symbol);
            _out[_outPos++] = (byte)(symbol - 0x100);
        }
    }
}
