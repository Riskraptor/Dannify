using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// Special days, when the installer dresses up a little: snow at
    /// Christmas, confetti for the New Year, and a greeting above the name.
    /// The same days as the app (frontend/src/model/occasions.js and
    /// Backend/dannify/occasions.py). Nothing moves when Windows is set to
    /// show no animations.
    /// </summary>
    internal static class Season
    {
        /// <summary>The day to dress for, in a preview (--ui-state) only.</summary>
        public static DateTime? Override { get; set; }

        public static DateTime Now => Override ?? DateTime.Now;

        /// <summary>"christmas", "newyear", or "" on any other day.</summary>
        public static string Today(DateTime when)
        {
            int md = when.Month * 100 + when.Day;
            if (md >= 1218 && md <= 1226) return "christmas";
            if (md >= 1231 || md <= 102) return "newyear";
            return "";
        }

        /// <summary>The greeting for the day, or "".</summary>
        public static string Greeting(DateTime when)
        {
            switch (Today(when))
            {
                case "christmas":
                    return S.MerryChristmas;
                case "newyear":
                    // The New Year a December 31 belongs to is the one it opens.
                    return S.HappyNewYear(when.Month == 12 ? when.Year + 1 : when.Year);
                default:
                    return "";
            }
        }

        private static readonly Color[] Confetti =
        {
            Color.FromRgb(0x1E, 0xD7, 0x60), Color.FromRgb(0xFF, 0xD1, 0x66), Color.FromRgb(0xEF, 0x47, 0x6F),
            Color.FromRgb(0x3F, 0xA9, 0xF5), Color.FromRgb(0xC7, 0x7D, 0xFF),
        };

        /// <summary>Put today's greeting and weather on the window, if it is a special day.</summary>
        public static void Decorate(SetupWindow window, DateTime when)
        {
            string occasion = Today(when);
            if (occasion.Length == 0) return;
            window.SeasonLine.Text = Greeting(when);
            window.SeasonLine.Visibility = Visibility.Visible;
            if (!Visuals.Motion) return;
            Fall(window.Weather, occasion == "christmas", window.ActualWidth, window.ActualHeight);
        }

        private static void Fall(Canvas canvas, bool snow, double width, double height)
        {
            var random = new Random();
            int count = snow ? 34 : 40;
            for (int i = 0; i < count; i++)
            {
                Shape piece;
                if (snow)
                {
                    double size = 2.5 + random.NextDouble() * 4.5;
                    piece = new Ellipse
                    {
                        Width = size,
                        Height = size,
                        Fill = Brushes.White,
                        Opacity = 0.35 + random.NextDouble() * 0.5,
                    };
                }
                else
                {
                    piece = new Rectangle
                    {
                        Width = 5,
                        Height = 9,
                        RadiusX = 1,
                        RadiusY = 1,
                        Fill = new SolidColorBrush(Confetti[i % Confetti.Length]),
                        Opacity = 0.9,
                    };
                }
                var fall = new TranslateTransform();
                var group = new TransformGroup();
                var spin = new RotateTransform();
                group.Children.Add(spin);
                group.Children.Add(fall);
                piece.RenderTransform = group;
                piece.RenderTransformOrigin = new Point(0.5, 0.5);
                piece.IsHitTestVisible = false;
                Canvas.SetLeft(piece, random.NextDouble() * width);
                Canvas.SetTop(piece, -12);
                canvas.Children.Add(piece);

                double seconds = snow ? 7 + random.NextDouble() * 7 : 4 + random.NextDouble() * 4;
                // Begun in the past, so the window opens with snow already falling.
                var start = TimeSpan.FromSeconds(-random.NextDouble() * seconds);
                fall.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(0, height + 24, TimeSpan.FromSeconds(seconds))
                {
                    RepeatBehavior = RepeatBehavior.Forever,
                    BeginTime = start,
                });
                fall.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-14 + random.NextDouble() * 6, 14 - random.NextDouble() * 6,
                    TimeSpan.FromSeconds(2.5 + random.NextDouble() * 2.5))
                {
                    RepeatBehavior = RepeatBehavior.Forever,
                    AutoReverse = true,
                    EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
                    BeginTime = start,
                });
                if (!snow)
                {
                    spin.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(0, 360 + random.Next(360), TimeSpan.FromSeconds(seconds))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        BeginTime = start,
                    });
                }
            }
        }
    }
}
