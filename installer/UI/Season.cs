using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using Dannify.Setup.Core;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// Special days, when the installer dresses up: the day's weather across
    /// the window and its greeting above the name. The very calendar the app
    /// uses (Occasions.json, made by packaging/make_occasions.py; the window
    /// reads frontend/src/model/occasions.json and the splash
    /// Backend/dannify/occasions.py), decided the same way: the days kept
    /// where the computer is, the most particular first. Nothing moves when
    /// Windows is set to show no animations; it is all there, holding still.
    /// </summary>
    internal static class Season
    {
        /// <summary>The day to dress for, in a preview (--ui-state) only.</summary>
        public static DateTime? Override { get; set; }

        /// <summary>The country to dress for, in a preview only.</summary>
        public static string RegionOverride { get; set; }

        public static DateTime Now => Override ?? DateTime.Now;

        private static Dictionary<string, object> _data;

        private static Dictionary<string, object> Data
        {
            get
            {
                if (_data != null) return _data;
                try
                {
                    using (var stream = typeof(Season).Assembly.GetManifestResourceStream("Occasions.json"))
                    using (var reader = new StreamReader(stream))
                        _data = Json.ParseObject(reader.ReadToEnd());
                }
                catch
                {
                    _data = new Dictionary<string, object>();
                }
                return _data;
            }
        }

        private static Dictionary<string, object> Obj(object o) => o as Dictionary<string, object>;
        private static List<object> List(object o) => o as List<object> ?? new List<object>();
        private static Dictionary<string, object> Get(Dictionary<string, object> o, string key) =>
            o != null && o.TryGetValue(key, out var v) ? Obj(v) : null;
        private static int Int(Dictionary<string, object> o, string key, int fallback)
        {
            if (o == null || !o.TryGetValue(key, out var v) || v == null) return fallback;
            try { return Convert.ToInt32(v, CultureInfo.InvariantCulture); } catch { return fallback; }
        }

        // --- Where the computer is -------------------------------------------------
        /// <summary>
        /// The country whose days are kept: the one the app last said (an
        /// update), else the time zone, with the Windows region or the
        /// language to choose among countries sharing it.
        /// </summary>
        public static string Region()
        {
            if (!string.IsNullOrEmpty(RegionOverride)) return RegionOverride;
            try
            {
                string dir = Environment.GetEnvironmentVariable("DANNIFY_DATA_DIR");
                string file = System.IO.Path.Combine(string.IsNullOrEmpty(dir) ? Env.DefaultData : dir, "window.json");
                if (File.Exists(file))
                {
                    string saved = Json.Str(Json.ParseObject(File.ReadAllText(file)), "region");
                    if (IsCode(saved)) return saved;
                }
            }
            catch
            {
                // a window.json being written as we read: the zone it is
            }
            string zone = "";
            try { zone = Json.Str(Get(Data, "windows"), TimeZoneInfo.Local.Id) ?? ""; } catch { }
            string system = "";
            try { system = RegionInfo.CurrentRegion.TwoLetterISORegionName.ToUpperInvariant(); } catch { }
            string fromLanguage = "";
            try
            {
                string[] parts = CultureInfo.CurrentUICulture.Name.Split('-');
                if (parts.Length > 1) fromLanguage = parts[parts.Length - 1].ToUpperInvariant();
            }
            catch { }
            return Detect(zone, system, fromLanguage);
        }

        /// <summary>The same reckoning as the app's detectRegion.</summary>
        public static string Detect(string zone, string system, string fromLanguage)
        {
            var zones = Get(Data, "zones");
            object listed = null;
            if (zones != null && !string.IsNullOrEmpty(zone)) zones.TryGetValue(zone, out listed);
            var sharing = List(listed).OfType<string>().ToList();
            if (!IsCode(system)) system = "";
            if (!IsCode(fromLanguage)) fromLanguage = "";
            if (sharing.Count > 0)
            {
                if (system.Length > 0 && sharing.Contains(system)) return system;
                if (fromLanguage.Length > 0 && sharing.Contains(fromLanguage)) return fromLanguage;
                return sharing[0];
            }
            return system.Length > 0 ? system : fromLanguage;
        }

        private static bool IsCode(string s) =>
            !string.IsNullOrEmpty(s) && s.Length == 2 && char.IsLetter(s[0]) && char.IsLetter(s[1]) && s == s.ToUpperInvariant();

        // --- Which day -------------------------------------------------------------
        public sealed class Day
        {
            public string Id;
            public string Kind;
            public string Country;
            public Dictionary<string, object> Names;
            public string Look;
            public int Priority;
            public DateTime On;
        }

        private static DateTime? StartIn(Dictionary<string, object> row, int year)
        {
            string md = Json.Str(row, "md");
            if (md != null)
            {
                string[] p = md.Split('-');
                try { return new DateTime(year, int.Parse(p[0], CultureInfo.InvariantCulture), int.Parse(p[1], CultureInfo.InvariantCulture)); }
                catch { return null; }
            }
            string iso = Json.Str(Get(row, "on"), year.ToString(CultureInfo.InvariantCulture));
            if (iso == null) return null;
            return DateTime.TryParseExact(iso, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var d)
                ? d : (DateTime?)null;
        }

        private static bool KeptIn(Dictionary<string, object> row, string region)
        {
            row.TryGetValue("where", out var where);
            if (where is string all && all == "*")
                return !(row.TryGetValue("unless", out var unless) && List(unless).OfType<string>().Contains(region));
            return !string.IsNullOrEmpty(region) && List(where).OfType<string>().Contains(region);
        }

        /// <summary>The day to dress for, or null.</summary>
        public static Day Today(DateTime when, string region)
        {
            var rows = new List<Dictionary<string, object>>();
            Data.TryGetValue("occasions", out var occasions);
            foreach (var r in List(occasions))
                if (Obj(r) is Dictionary<string, object> row && KeptIn(row, region)) rows.Add(row);
            var national = Get(Data, "national");
            if (!string.IsNullOrEmpty(region) && national != null && national.TryGetValue(region, out var mine))
            {
                foreach (var n in List(mine))
                {
                    if (!(Obj(n) is Dictionary<string, object> row)) continue;
                    rows.Add(new Dictionary<string, object>(row)
                    {
                        ["kind"] = "national",
                        ["look"] = region == "IE" ? "shamrock" : "flag",
                        ["priority"] = 40,
                        ["days"] = 1,
                        ["day"] = 0,
                    });
                }
            }
            DateTime today = when.Date;
            var found = new List<Day>();
            foreach (var row in rows)
            {
                foreach (int year in new[] { today.Year - 1, today.Year })
                {
                    DateTime? start = StartIn(row, year);
                    if (start == null) continue;
                    if (today < start.Value || today >= start.Value.AddDays(Int(row, "days", 1))) continue;
                    found.Add(new Day
                    {
                        Id = Json.Str(row, "id"),
                        Kind = Json.Str(row, "kind"),
                        Country = region,
                        Names = Get(row, "names"),
                        Look = Json.Str(row, "look"),
                        Priority = Int(row, "priority", 0),
                        On = start.Value.AddDays(Int(row, "day", 0)),
                    });
                }
            }
            return found.OrderByDescending(d => d.On == today ? 1 : 0).ThenByDescending(d => d.Priority).FirstOrDefault();
        }

        // --- What it says ----------------------------------------------------------
        private static readonly Dictionary<string, string[]> Titles = new Dictionary<string, string[]>
        {
            ["christmas"] = new[] { "Merry Christmas", "Joyeux Noël" },
            ["orthodox_christmas"] = new[] { "Merry Christmas", "Joyeux Noël" },
            ["lunar_new_year"] = new[] { "Happy Lunar New Year", "Joyeux Nouvel An lunaire" },
            ["valentines"] = new[] { "Happy Valentine’s Day", "Joyeuse Saint-Valentin" },
            ["womens_day"] = new[] { "Happy International Women’s Day", "Bonne Journée des droits des femmes" },
            ["holi"] = new[] { "Happy Holi", "Joyeuse Holi" },
            ["nowruz"] = new[] { "Happy Nowruz", "Joyeux Norouz" },
            ["ramadan"] = new[] { "Ramadan Mubarak", "Ramadan Moubarak" },
            ["eid_fitr"] = new[] { "Eid Mubarak", "Aïd Moubarak" },
            ["eid_adha"] = new[] { "Eid al-Adha Mubarak", "Aïd el-Kébir Moubarak" },
            ["easter"] = new[] { "Happy Easter", "Joyeuses Pâques" },
            ["orthodox_easter"] = new[] { "Happy Easter", "Joyeuses Pâques" },
            ["vesak"] = new[] { "Happy Vesak", "Joyeux Vesak" },
            ["world_music_day"] = new[] { "Happy World Music Day", "Bonne Fête de la musique" },
            ["mid_autumn"] = new[] { "Happy Mid-Autumn Festival", "Bonne fête de la Mi-Automne" },
            ["rosh_hashanah"] = new[] { "Shana Tova", "Shana Tova" },
            ["diwali"] = new[] { "Happy Diwali", "Joyeux Diwali" },
            ["halloween"] = new[] { "Happy Halloween", "Joyeux Halloween" },
            ["day_of_dead"] = new[] { "Día de Muertos", "Día de Muertos" },
            ["thanksgiving"] = new[] { "Happy Thanksgiving", "Joyeux Thanksgiving" },
            ["thanksgiving_ca"] = new[] { "Happy Thanksgiving", "Joyeuse Action de grâce" },
            ["hanukkah"] = new[] { "Happy Hanukkah", "Joyeux Hanoukka" },
            ["mothers_day"] = new[] { "Happy Mother’s Day", "Bonne fête des mères" },
            ["fathers_day"] = new[] { "Happy Father’s Day", "Bonne fête des pères" },
        };

        /// <summary>The greeting for the day, or "".</summary>
        public static string Greeting(Day day)
        {
            if (day == null) return "";
            if (day.Kind == "national")
            {
                string name = Json.Str(day.Names, S.French ? "fr" : "en") ?? Json.Str(day.Names, "en") ?? "";
                return S.French ? name + " : bonne fête !" : "Happy " + name + "!";
            }
            if (day.Id == "newyear")
                return S.HappyNewYear(day.On.Month == 12 ? day.On.Year + 1 : day.On.Year);
            return Titles.TryGetValue(day.Id ?? "", out var t) ? (S.French ? t[1] : t[0]) : "";
        }

        // --- How it looks ----------------------------------------------------------
        private static void LookOf(Day day, out string shape, out string motion, out List<Color> palette)
        {
            shape = "ribbon";
            motion = "fall";
            palette = new List<Color>();
            object colours = null;
            if (day.Look == "flag")
            {
                Get(Data, "flags")?.TryGetValue(day.Country ?? "", out colours);
            }
            else
            {
                var looks = Get(Data, "looks");
                var look = Get(looks, day.Look ?? "") ?? Get(looks, "confetti");
                shape = Json.Str(look, "shape") ?? shape;
                motion = Json.Str(look, "motion") ?? motion;
                look?.TryGetValue("palette", out colours);
            }
            foreach (var c in List(colours).OfType<string>())
            {
                try { palette.Add((Color)ColorConverter.ConvertFromString(c)); } catch { }
            }
            if (palette.Count == 0) palette.Add(Colors.White);
        }

        /// <summary>Put today's greeting and weather on the window, if it is a special day.</summary>
        public static void Decorate(SetupWindow window, DateTime when)
        {
            Day day;
            try { day = Today(when, Region()); }
            catch { day = null; }
            if (day == null) return;
            window.SeasonLine.Text = Greeting(day);
            window.SeasonLine.Visibility = Visibility.Visible;
            LookOf(day, out string shape, out string motion, out List<Color> palette);
            Fall(window.Weather, shape, motion, palette, window.ActualWidth, window.ActualHeight, Visuals.Motion);
        }

        private static readonly Dictionary<string, string> Glyphs = new Dictionary<string, string>
        {
            ["heart"] = "♥", ["star"] = "✦", ["note"] = "♪", ["clover"] = "☘",
        };

        private static FrameworkElement Piece(string shape, Color colour, Random random)
        {
            var brush = new SolidColorBrush(colour);
            switch (shape)
            {
                case "dot":
                {
                    double size = 2.5 + random.NextDouble() * 4.5;
                    return new Ellipse { Width = size, Height = size, Fill = brush, Opacity = 0.35 + random.NextDouble() * 0.5 };
                }
                case "ribbon":
                    return new Rectangle { Width = 5, Height = 9, RadiusX = 1, RadiusY = 1, Fill = brush, Opacity = 0.9 };
                case "leaf":
                case "petal":
                {
                    double size = 8 + random.NextDouble() * 6;
                    return new Ellipse { Width = size * 0.6, Height = size, Fill = brush, Opacity = 0.85 };
                }
                case "lantern":
                    return new Rectangle
                    {
                        Width = 11, Height = 15, RadiusX = 4, RadiusY = 4, Fill = brush, Opacity = 0.9,
                        Effect = new System.Windows.Media.Effects.DropShadowEffect { Color = colour, BlurRadius = 12, ShadowDepth = 0 },
                    };
                case "flame":
                case "spark":
                {
                    double size = 3.5 + random.NextDouble() * 3;
                    return new Ellipse
                    {
                        Width = size, Height = size, Fill = brush,
                        Effect = new System.Windows.Media.Effects.DropShadowEffect { Color = colour, BlurRadius = 10, ShadowDepth = 0 },
                    };
                }
                case "puff":
                {
                    double size = 60 + random.NextDouble() * 80;
                    var fill = new RadialGradientBrush(colour, Color.FromArgb(0, colour.R, colour.G, colour.B));
                    return new Ellipse { Width = size, Height = size, Fill = fill, Opacity = 0.3 };
                }
                default:
                    return new TextBlock
                    {
                        Text = Glyphs.TryGetValue(shape, out var g) ? g : "✦",
                        FontSize = 11 + random.Next(8),
                        Foreground = brush,
                        Opacity = 0.9,
                    };
            }
        }

        private static void Fall(Canvas canvas, string shape, string motion, List<Color> palette, double width, double height, bool moving)
        {
            var random = new Random();
            int count = shape == "puff" ? 14 : 36;
            bool travels = motion == "fall" || motion == "rise";
            for (int i = 0; i < count; i++)
            {
                FrameworkElement piece = Piece(shape, palette[i % palette.Count], random);
                var move = new TranslateTransform();
                var spin = new RotateTransform(random.Next(-30, 30));
                var scale = new ScaleTransform(1, 1);
                var group = new TransformGroup();
                group.Children.Add(scale);
                group.Children.Add(spin);
                group.Children.Add(move);
                piece.RenderTransform = group;
                piece.RenderTransformOrigin = new Point(0.5, 0.5);
                piece.IsHitTestVisible = false;
                Canvas.SetLeft(piece, random.NextDouble() * width);
                // Still, or twinkling where it is: anywhere on the window.
                // Falling or rising: from the edge it comes in at.
                double y = random.NextDouble() * height;
                Canvas.SetTop(piece, !moving || !travels ? y : motion == "fall" ? -16 : height + 16);
                canvas.Children.Add(piece);
                if (!moving) continue;

                double seconds = travels ? 6 + random.NextDouble() * 7 : 2.2 + random.NextDouble() * 2.2;
                // Begun in the past, so the window opens with it all under way.
                var start = TimeSpan.FromSeconds(-random.NextDouble() * seconds);
                if (travels)
                {
                    double distance = (height + 32) * (motion == "fall" ? 1 : -1);
                    move.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(0, distance, TimeSpan.FromSeconds(seconds))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        BeginTime = start,
                    });
                    move.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-14 + random.NextDouble() * 6, 14 - random.NextDouble() * 6,
                        TimeSpan.FromSeconds(2.5 + random.NextDouble() * 2.5))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        AutoReverse = true,
                        EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
                        BeginTime = start,
                    });
                    if (shape == "ribbon" || shape == "leaf" || shape == "petal")
                    {
                        spin.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(0, 360 + random.Next(360), TimeSpan.FromSeconds(seconds))
                        {
                            RepeatBehavior = RepeatBehavior.Forever,
                            BeginTime = start,
                        });
                    }
                }
                else
                {
                    // Twinkling, bursting or drifting where it is.
                    var pulse = new DoubleAnimation(0.35, motion == "drift" ? 1.25 : 1.0, TimeSpan.FromSeconds(seconds / 2))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        AutoReverse = true,
                        EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
                        BeginTime = start,
                    };
                    scale.BeginAnimation(ScaleTransform.ScaleXProperty, pulse);
                    scale.BeginAnimation(ScaleTransform.ScaleYProperty, pulse);
                    piece.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0.15, piece.Opacity, TimeSpan.FromSeconds(seconds / 2))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        AutoReverse = true,
                        BeginTime = start,
                    });
                }
            }
        }
    }
}
