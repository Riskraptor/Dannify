using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// Just enough JSON to read the app's small files (settings.json, the
    /// update marker). .NET Framework has no JSON reader of its own that is
    /// not either slow to load or tied to web assemblies.
    /// </summary>
    internal static class Json
    {
        public static object Parse(string text)
        {
            int i = 0;
            object value = ReadValue(text, ref i);
            SkipSpace(text, ref i);
            if (i != text.Length) throw new FormatException("trailing characters");
            return value;
        }

        public static Dictionary<string, object> ParseObject(string text) =>
            Parse(text) as Dictionary<string, object> ?? throw new FormatException("not an object");

        public static string Str(Dictionary<string, object> o, string key) =>
            o != null && o.TryGetValue(key, out var v) && v is string s ? s : null;

        private static void SkipSpace(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        private static object ReadValue(string s, ref int i)
        {
            SkipSpace(s, ref i);
            if (i >= s.Length) throw new FormatException("unexpected end");
            char c = s[i];
            switch (c)
            {
                case '{': return ReadObject(s, ref i);
                case '[': return ReadArray(s, ref i);
                case '"': return ReadString(s, ref i);
                case 't': Expect(s, ref i, "true"); return true;
                case 'f': Expect(s, ref i, "false"); return false;
                case 'n': Expect(s, ref i, "null"); return null;
                default: return ReadNumber(s, ref i);
            }
        }

        private static void Expect(string s, ref int i, string word)
        {
            if (string.CompareOrdinal(s, i, word, 0, word.Length) != 0) throw new FormatException("bad literal");
            i += word.Length;
        }

        private static Dictionary<string, object> ReadObject(string s, ref int i)
        {
            var o = new Dictionary<string, object>(StringComparer.Ordinal);
            i++;
            SkipSpace(s, ref i);
            if (i < s.Length && s[i] == '}')
            {
                i++;
                return o;
            }
            while (true)
            {
                SkipSpace(s, ref i);
                if (i >= s.Length || s[i] != '"') throw new FormatException("expected key");
                string key = ReadString(s, ref i);
                SkipSpace(s, ref i);
                if (i >= s.Length || s[i] != ':') throw new FormatException("expected colon");
                i++;
                o[key] = ReadValue(s, ref i);
                SkipSpace(s, ref i);
                if (i >= s.Length) throw new FormatException("unexpected end");
                if (s[i] == ',')
                {
                    i++;
                    continue;
                }
                if (s[i] == '}')
                {
                    i++;
                    return o;
                }
                throw new FormatException("expected , or }");
            }
        }

        private static List<object> ReadArray(string s, ref int i)
        {
            var a = new List<object>();
            i++;
            SkipSpace(s, ref i);
            if (i < s.Length && s[i] == ']')
            {
                i++;
                return a;
            }
            while (true)
            {
                a.Add(ReadValue(s, ref i));
                SkipSpace(s, ref i);
                if (i >= s.Length) throw new FormatException("unexpected end");
                if (s[i] == ',')
                {
                    i++;
                    continue;
                }
                if (s[i] == ']')
                {
                    i++;
                    return a;
                }
                throw new FormatException("expected , or ]");
            }
        }

        private static string ReadString(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++;
            while (i < s.Length)
            {
                char c = s[i++];
                if (c == '"') return sb.ToString();
                if (c != '\\')
                {
                    sb.Append(c);
                    continue;
                }
                if (i >= s.Length) break;
                char e = s[i++];
                switch (e)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 > s.Length) throw new FormatException("bad escape");
                        sb.Append((char)int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                        i += 4;
                        break;
                    default: throw new FormatException("bad escape");
                }
            }
            throw new FormatException("unterminated string");
        }

        private static object ReadNumber(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            if (start == i) throw new FormatException("unexpected character");
            return double.Parse(s.Substring(start, i - start), NumberStyles.Float, CultureInfo.InvariantCulture);
        }
    }
}
