using System;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Dannify.Setup.Core;

namespace Dannify.Setup.UI
{
    /// <summary>Window chrome and motion, shared by both windows.</summary>
    internal static class Visuals
    {
        /// <summary>
        /// Windows' "Show animations" setting, and high contrast, both mean
        /// keep still: every transition becomes instant.
        /// </summary>
        public static bool Motion => SystemParameters.ClientAreaAnimation && !SystemParameters.HighContrast;

        public static bool IsWindows11 => Environment.OSVersion.Version.Build >= 22000;

        public static void Chrome(Window window)
        {
            try
            {
                IntPtr hwnd = new WindowInteropHelper(window).Handle;
                int round = Native.DWMWCP_ROUND;
                Native.DwmSetWindowAttribute(hwnd, Native.DWMWA_WINDOW_CORNER_PREFERENCE, ref round, 4);
                int dark = 1;
                Native.DwmSetWindowAttribute(hwnd, Native.DWMWA_USE_IMMERSIVE_DARK_MODE, ref dark, 4);
                int border = 0x002C302E; // COLORREF (BGR): a quiet edge on dark desktops
                Native.DwmSetWindowAttribute(hwnd, Native.DWMWA_BORDER_COLOR, ref border, 4);
            }
            catch
            {
                // Windows 10: square corners, no coloured border. That is fine.
            }
        }

        public static IEasingFunction Out => new CubicEase { EasingMode = EasingMode.EaseOut };
        public static IEasingFunction Spring => new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.35 };

        public static Duration Ms(int ms) => new Duration(TimeSpan.FromMilliseconds(Motion ? ms : 0));

        public static void Animate(Animatable target, DependencyProperty property, double to, int ms,
            IEasingFunction ease = null, Action done = null, double? from = null)
        {
            var anim = new DoubleAnimation
            {
                To = to,
                Duration = Ms(ms),
                EasingFunction = ease ?? Out,
                FillBehavior = FillBehavior.HoldEnd,
            };
            if (from.HasValue) anim.From = from.Value;
            if (done != null) anim.Completed += (s, e) => done();
            target.BeginAnimation(property, anim);
        }

        public static void Animate(UIElement target, DependencyProperty property, double to, int ms,
            IEasingFunction ease = null, Action done = null, double? from = null)
        {
            var anim = new DoubleAnimation
            {
                To = to,
                Duration = Ms(ms),
                EasingFunction = ease ?? Out,
                FillBehavior = FillBehavior.HoldEnd,
            };
            if (from.HasValue) anim.From = from.Value;
            if (done != null) anim.Completed += (s, e) => done();
            target.BeginAnimation(property, anim);
        }

        /// <summary>Fade and lift an element into view.</summary>
        public static void Enter(FrameworkElement e, int delay = 0, double lift = 10)
        {
            e.Visibility = Visibility.Visible;
            var shift = e.RenderTransform as TranslateTransform;
            if (shift == null || shift.IsFrozen)
            {
                shift = new TranslateTransform();
                e.RenderTransform = shift;
            }
            if (!Motion)
            {
                e.BeginAnimation(UIElement.OpacityProperty, null);
                e.Opacity = 1;
                shift.BeginAnimation(TranslateTransform.YProperty, null);
                shift.Y = 0;
                return;
            }
            var begin = TimeSpan.FromMilliseconds(delay);
            e.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, new Duration(TimeSpan.FromMilliseconds(260)))
            {
                BeginTime = begin,
                EasingFunction = Out,
            });
            shift.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(lift, 0, new Duration(TimeSpan.FromMilliseconds(320)))
            {
                BeginTime = begin,
                EasingFunction = Out,
            });
        }

        /// <summary>Fade an element out, then collapse it.</summary>
        public static void Leave(FrameworkElement e, Action done = null)
        {
            if (e.Visibility != Visibility.Visible)
            {
                done?.Invoke();
                return;
            }
            if (!Motion)
            {
                e.BeginAnimation(UIElement.OpacityProperty, null);
                e.Visibility = Visibility.Collapsed;
                done?.Invoke();
                return;
            }
            var anim = new DoubleAnimation(e.Opacity, 0, new Duration(TimeSpan.FromMilliseconds(140))) { EasingFunction = Out };
            anim.Completed += (s, a) =>
            {
                e.Visibility = Visibility.Collapsed;
                done?.Invoke();
            };
            e.BeginAnimation(UIElement.OpacityProperty, anim);
        }

        /// <summary>A value that drifts back and forth for ever (background glow, breathing).</summary>
        public static void Drift(Animatable target, DependencyProperty property, double from, double to, double seconds, double delay = 0)
        {
            if (!Motion) return;
            target.BeginAnimation(property, new DoubleAnimation(from, to, new Duration(TimeSpan.FromSeconds(seconds)))
            {
                AutoReverse = true,
                RepeatBehavior = RepeatBehavior.Forever,
                BeginTime = TimeSpan.FromSeconds(delay),
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            });
        }

        public static void Drift(UIElement target, DependencyProperty property, double from, double to, double seconds, double delay = 0)
        {
            if (!Motion) return;
            target.BeginAnimation(property, new DoubleAnimation(from, to, new Duration(TimeSpan.FromSeconds(seconds)))
            {
                AutoReverse = true,
                RepeatBehavior = RepeatBehavior.Forever,
                BeginTime = TimeSpan.FromSeconds(delay),
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            });
        }

        /// <summary>A long path shortened in the middle, so both the drive and the folder name show.</summary>
        public static string MiddleTrim(string path, int max = 52)
        {
            if (string.IsNullOrEmpty(path) || path.Length <= max) return path;
            int keepEnd = max / 2;
            int keepStart = max - keepEnd - 1;
            return path.Substring(0, keepStart) + "…" + path.Substring(path.Length - keepEnd);
        }
    }
}
