using System;
using System.Globalization;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Shell;
using System.Windows.Threading;

namespace Dannify.Setup.UI
{
    internal enum HeroState
    {
        Logo,
        Check,
        Warn,
    }

    /// <summary>
    /// The installer's window. It only knows how to look: what to show and
    /// when is decided by the flows in Flows.cs.
    /// </summary>
    public partial class SetupWindow : Window
    {
        private FrameworkElement _page;
        private readonly DispatcherTimer _tick;
        private double _target;
        private double _shown;
        private bool _sweeping;
        private TaskCompletionSource<bool> _answer;
        private bool _closing;

        /// <summary>While true the window cannot be closed (the swap is running).</summary>
        public bool CloseLocked { get; set; }

        /// <summary>X, Escape, Alt+F4: the flow decides what closing means right now.</summary>
        public Action CloseRequested { get; set; }

        public SetupWindow()
        {
            InitializeComponent();
            LogoImage.Source = Logo.Build();
            AutomationProperties.SetName(MinButton, S.Minimize);
            AutomationProperties.SetName(CloseButton, S.Close);
            AutomationProperties.SetName(SheetClose, S.Close);
            MinButton.Click += (s, e) => WindowState = WindowState.Minimized;
            CloseButton.Click += (s, e) => RequestClose();
            SheetClose.Click += (s, e) => CloseSheet();
            SheetDim.MouseLeftButtonDown += (s, e) => CloseSheet();
            ConfirmYes.Click += (s, e) => Answer(true);
            ConfirmNo.Click += (s, e) => Answer(false);
            Root.MouseLeftButtonDown += (s, e) =>
            {
                if (e.ChangedButton == MouseButton.Left && e.ButtonState == MouseButtonState.Pressed && !e.Handled)
                {
                    try
                    {
                        DragMove();
                    }
                    catch (InvalidOperationException)
                    {
                        // the button was released already
                    }
                }
            };
            PreviewKeyDown += OnKey;
            Closing += (s, e) =>
            {
                if (_closing) return;
                e.Cancel = true;
                RequestClose();
            };
            SourceInitialized += (s, e) =>
            {
                Visuals.Chrome(this);
                if (!Visuals.IsWindows11) Edge.Visibility = Visibility.Visible;
            };
            Loaded += (s, e) => Intro();

            _tick = new DispatcherTimer(DispatcherPriority.Render) { Interval = TimeSpan.FromMilliseconds(16) };
            _tick.Tick += (s, e) => StepBar();
        }

        private void Intro()
        {
            Visuals.Animate(this, OpacityProperty, 1, 240, from: 0);
            Visuals.Drift(GlowAShift, TranslateTransform.XProperty, -40, 50, 9);
            Visuals.Drift(GlowAShift, TranslateTransform.YProperty, -12, 28, 11, 1);
            Visuals.Drift(GlowBShift, TranslateTransform.XProperty, 40, -50, 10, 0.5);
            Visuals.Drift(GlowBShift, TranslateTransform.YProperty, 24, -24, 12, 2);
            Visuals.Drift(HeroGlow, OpacityProperty, 0.6, 1.0, 2.8);
            if (Visuals.Motion)
            {
                Visuals.Animate(LogoScale, ScaleTransform.ScaleXProperty, 1, 620, Visuals.Spring, from: 0.86);
                Visuals.Animate(LogoScale, ScaleTransform.ScaleYProperty, 1, 620, Visuals.Spring, from: 0.86);
            }
        }

        // ----------------------------------------------------------------
        // Pages and the mark
        // ----------------------------------------------------------------

        internal void ShowPage(FrameworkElement page)
        {
            if (_page == page)
            {
                Visuals.Enter(page, 0, 0);
                return;
            }
            var old = _page;
            _page = page;
            // The version belongs with the first question, not under a result.
            bool footer = page == WelcomePage || page == RemovePage;
            Visuals.Animate(Footer, OpacityProperty, footer ? 1 : 0, 200);
            foreach (var p in new FrameworkElement[] { WelcomePage, ProgressPage, ResultPage, RemovePage })
                if (p != page && p != old) p.Visibility = Visibility.Collapsed;
            if (old == null)
            {
                Visuals.Enter(page, 80);
                FocusFirst(page);
                return;
            }
            Visuals.Leave(old, () =>
            {
                Visuals.Enter(page);
                FocusFirst(page);
            });
        }

        private static void FocusFirst(FrameworkElement page)
        {
            page.Dispatcher.BeginInvoke(new Action(() =>
            {
                if (page is Panel panel)
                    foreach (var child in panel.Children)
                        if (FindButton(child as DependencyObject) is Control c && c.IsVisible && c.IsEnabled)
                        {
                            c.Focus();
                            return;
                        }
            }), DispatcherPriority.Input);
        }

        private static Control FindButton(DependencyObject node)
        {
            if (node == null) return null;
            if (node is Button b && b.Visibility == Visibility.Visible) return b;
            if (node is Panel p)
                foreach (var child in p.Children)
                {
                    var hit = FindButton(child as DependencyObject);
                    if (hit != null) return hit;
                }
            return null;
        }

        internal void SetHero(HeroState state)
        {
            bool logo = state == HeroState.Logo;
            Visuals.Animate(LogoImage, OpacityProperty, logo ? 1 : 0, 220);
            Visuals.Animate(LogoScale, ScaleTransform.ScaleXProperty, logo ? 1 : 0.7, 320);
            Visuals.Animate(LogoScale, ScaleTransform.ScaleYProperty, logo ? 1 : 0.7, 320);

            Badge(CheckBadge, CheckScale, state == HeroState.Check);
            Badge(WarnBadge, WarnScale, state == HeroState.Warn);
            if (state == HeroState.Check)
            {
                CheckPath.BeginAnimation(Shape.StrokeDashOffsetProperty, new DoubleAnimation(8, 0, Visuals.Ms(520))
                {
                    BeginTime = TimeSpan.FromMilliseconds(Visuals.Motion ? 200 : 0),
                    EasingFunction = Visuals.Out,
                });
            }

            var tint = state == HeroState.Warn ? Color.FromRgb(0xFF, 0xB5, 0x47) : Color.FromRgb(0x1A, 0xD0, 0x5C);
            var glow = new RadialGradientBrush();
            glow.GradientStops.Add(new GradientStop(Color.FromArgb(0x5A, tint.R, tint.G, tint.B), 0));
            glow.GradientStops.Add(new GradientStop(Color.FromArgb(0x1A, tint.R, tint.G, tint.B), 0.5));
            glow.GradientStops.Add(new GradientStop(Color.FromArgb(0x00, tint.R, tint.G, tint.B), 1));
            HeroGlow.Fill = glow;
        }

        private static void Badge(FrameworkElement badge, ScaleTransform scale, bool show)
        {
            Visuals.Animate(badge, OpacityProperty, show ? 1 : 0, show ? 220 : 160);
            Visuals.Animate(scale, ScaleTransform.ScaleXProperty, show ? 1 : 0.6, show ? 560 : 200, show ? Visuals.Spring : null);
            Visuals.Animate(scale, ScaleTransform.ScaleYProperty, show ? 1 : 0.6, show ? 560 : 200, show ? Visuals.Spring : null);
        }

        // ----------------------------------------------------------------
        // Progress: the bar glides toward the real number instead of jumping
        // ----------------------------------------------------------------

        internal void SetProgress(double fraction, string step)
        {
            if (_sweeping) StopSweep();
            _target = Math.Max(_target, Math.Max(0, Math.Min(1, fraction)));
            ProgressStep.Text = step;
            Taskbar.ProgressState = TaskbarItemProgressState.Normal;
            Taskbar.ProgressValue = _target;
            if (!_tick.IsEnabled)
            {
                _tick.Start();
                if (Visuals.Motion)
                {
                    ShimmerShift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-120, 400, new Duration(TimeSpan.FromSeconds(1.7)))
                    {
                        RepeatBehavior = RepeatBehavior.Forever,
                        EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
                    });
                }
            }
        }

        internal void ResetProgress()
        {
            _target = 0;
            _shown = 0;
            BarFill.Width = 0;
            ProgressPercent.Text = "";
            Taskbar.ProgressState = TaskbarItemProgressState.None;
        }

        /// <summary>No number to show (closing the app, waiting): a sweeping bar.</summary>
        internal void SetWaiting(string step)
        {
            ProgressStep.Text = step;
            ProgressPercent.Text = "";
            Taskbar.ProgressState = TaskbarItemProgressState.Indeterminate;
            if (_sweeping) return;
            _sweeping = true;
            BarFill.Visibility = Visibility.Collapsed;
            BarSweep.Visibility = Visibility.Visible;
            SweepShift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-120, 380, new Duration(TimeSpan.FromSeconds(1.25)))
            {
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            });
        }

        private void StopSweep()
        {
            _sweeping = false;
            SweepShift.BeginAnimation(TranslateTransform.XProperty, null);
            BarSweep.Visibility = Visibility.Collapsed;
            BarFill.Visibility = Visibility.Visible;
        }

        private void StepBar()
        {
            double gap = _target - _shown;
            _shown = Math.Abs(gap) < 0.0008 || !Visuals.Motion ? _target : _shown + gap * 0.16;
            BarFill.Width = Math.Max(0, Bar.ActualWidth * _shown);
            int percent = (int)Math.Round(_shown * 100);
            ProgressPercent.Text = S.French
                ? percent.ToString(CultureInfo.InvariantCulture) + " %"
                : percent.ToString(CultureInfo.InvariantCulture) + "%";
        }

        internal void ProgressDone()
        {
            _target = 1;
            Taskbar.ProgressState = TaskbarItemProgressState.None;
        }

        // ----------------------------------------------------------------
        // The options sheet
        // ----------------------------------------------------------------

        internal bool SheetOpen => Sheet.Visibility == Visibility.Visible;

        internal void OpenSheet()
        {
            Sheet.Visibility = Visibility.Visible;
            Visuals.Animate(SheetDim, OpacityProperty, 1, 200, from: 0);
            Visuals.Animate(SheetShift, TranslateTransform.YProperty, 0, 360, from: 380);
            Dispatcher.BeginInvoke(new Action(() => OptDesktop.Focus()), DispatcherPriority.Input);
        }

        internal void CloseSheet(Action done = null)
        {
            if (!SheetOpen)
            {
                done?.Invoke();
                return;
            }
            Visuals.Animate(SheetDim, OpacityProperty, 0, 200);
            Visuals.Animate(SheetShift, TranslateTransform.YProperty, 380, 240, new CubicEase { EasingMode = EasingMode.EaseIn }, () =>
            {
                Sheet.Visibility = Visibility.Collapsed;
                done?.Invoke();
            });
        }

        // ----------------------------------------------------------------
        // Questions
        // ----------------------------------------------------------------

        internal Task<bool> Ask(string title, string text, string yes, string no)
        {
            _answer?.TrySetResult(false);
            _answer = new TaskCompletionSource<bool>();
            ConfirmTitle.Text = title;
            ConfirmText.Text = text;
            ConfirmYes.Content = yes;
            ConfirmNo.Content = no;
            Confirm.Visibility = Visibility.Visible;
            Visuals.Animate(Confirm, OpacityProperty, 1, 180, from: 0);
            Dispatcher.BeginInvoke(new Action(() => ConfirmNo.Focus()), DispatcherPriority.Input);
            return _answer.Task;
        }

        private void Answer(bool yes)
        {
            Visuals.Animate(Confirm, OpacityProperty, 0, 140, null, () => Confirm.Visibility = Visibility.Collapsed);
            var answer = _answer;
            _answer = null;
            answer?.TrySetResult(yes);
        }

        // ----------------------------------------------------------------
        // Closing
        // ----------------------------------------------------------------

        private void OnKey(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Escape) return;
            e.Handled = true;
            if (Confirm.Visibility == Visibility.Visible)
            {
                Answer(false);
                return;
            }
            if (SheetOpen)
            {
                CloseSheet();
                return;
            }
            RequestClose();
        }

        private void RequestClose()
        {
            if (CloseLocked) return;
            if (CloseRequested != null) CloseRequested();
            else CloseNow();
        }

        /// <summary>Fade out and close, whatever state the window is in.</summary>
        public void CloseNow()
        {
            if (_closing) return;
            _closing = true;
            _tick.Stop();
            Visuals.Animate(this, OpacityProperty, 0, 160, null, () => Close());
        }
    }
}
