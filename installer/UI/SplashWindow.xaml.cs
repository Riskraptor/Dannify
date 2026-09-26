using System;
using System.Globalization;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shell;
using System.Windows.Threading;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// The small window for work nobody has to decide anything about: an
    /// update started from inside Dannify, and the moment between closing the
    /// old version and the new one appearing.
    /// </summary>
    public partial class SplashWindow : Window
    {
        private readonly DispatcherTimer _tick;
        private double _target;
        private double _shown;
        private bool _sweeping;
        private bool _closing;

        public SplashWindow()
        {
            InitializeComponent();
            LogoImage.Source = Logo.Build();
            SourceInitialized += (s, e) =>
            {
                Visuals.Chrome(this);
                if (!Visuals.IsWindows11) Edge.Visibility = Visibility.Visible;
            };
            Loaded += (s, e) =>
            {
                Visuals.Animate(this, OpacityProperty, 1, 220, from: 0);
                Visuals.Drift(GlowShift, TranslateTransform.XProperty, -20, 40, 6);
                Visuals.Drift(LogoScale, ScaleTransform.ScaleXProperty, 1, 1.05, 1.4);
                Visuals.Drift(LogoScale, ScaleTransform.ScaleYProperty, 1, 1.05, 1.4);
            };
            Closing += (s, e) =>
            {
                // Nothing to cancel from here: the work finishes on its own.
                if (!_closing) e.Cancel = true;
            };
            _tick = new DispatcherTimer(DispatcherPriority.Render) { Interval = TimeSpan.FromMilliseconds(16) };
            _tick.Tick += (s, e) =>
            {
                double gap = _target - _shown;
                _shown = Math.Abs(gap) < 0.0008 || !Visuals.Motion ? _target : _shown + gap * 0.16;
                BarFill.Width = Math.Max(0, Bar.ActualWidth * _shown);
                int percent = (int)Math.Round(_shown * 100);
                Percent.Text = percent.ToString(CultureInfo.InvariantCulture) + (S.French ? " %" : "%");
            };
        }

        /// <summary>Sit where the app's window was, so the change reads as one thing.</summary>
        internal void PlaceOver(Core.Native.RECT rect)
        {
            if (rect.Right - rect.Left < 200) return;
            WindowStartupLocation = WindowStartupLocation.Manual;
            double scale = 1.0;
            try
            {
                var dpi = VisualTreeHelper.GetDpi(this);
                scale = dpi.DpiScaleX;
            }
            catch
            {
                // default scale
            }
            double cx = (rect.Left + rect.Right) / 2.0 / scale;
            double cy = (rect.Top + rect.Bottom) / 2.0 / scale;
            Left = cx - Width / 2;
            Top = cy - Height / 2;
        }

        internal void SetHeading(string text) => Heading.Text = text;

        internal void SetProgress(double fraction, string step)
        {
            if (_sweeping)
            {
                _sweeping = false;
                SweepShift.BeginAnimation(TranslateTransform.XProperty, null);
                BarSweep.Visibility = Visibility.Collapsed;
                BarFill.Visibility = Visibility.Visible;
            }
            _target = Math.Max(_target, Math.Max(0, Math.Min(1, fraction)));
            Step.Text = step;
            Taskbar.ProgressState = TaskbarItemProgressState.Normal;
            Taskbar.ProgressValue = _target;
            if (!_tick.IsEnabled) _tick.Start();
        }

        internal void SetWaiting(string step)
        {
            Step.Text = step;
            Percent.Text = "";
            Taskbar.ProgressState = TaskbarItemProgressState.Indeterminate;
            if (_sweeping) return;
            _sweeping = true;
            _tick.Stop();
            BarFill.Visibility = Visibility.Collapsed;
            BarSweep.Visibility = Visibility.Visible;
            SweepShift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-90, 380, new Duration(TimeSpan.FromSeconds(1.2)))
            {
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            });
        }

        public void CloseNow()
        {
            if (_closing) return;
            _closing = true;
            _tick.Stop();
            Visuals.Animate(this, OpacityProperty, 0, 180, null, () => Close());
        }
    }
}
