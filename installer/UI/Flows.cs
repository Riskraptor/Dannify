using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;
using Dannify.Setup.Core;

namespace Dannify.Setup.UI
{
    /// <summary>The WPF application: one per run, shut down when the last window closes.</summary>
    internal static class Ui
    {
        public static Application App;
        public static int ExitCode;

        public static void Boot()
        {
            App = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            // Every await in the flows has to come back to the window's thread.
            // Without this, work started before the message loop runs resumes
            // on a pool thread, and the first touch of a window there throws.
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(App.Dispatcher));
            App.Resources.MergedDictionaries.Add(new ResourceDictionary
            {
                Source = new Uri("pack://application:,,,/DannifySetup;component/UI/Theme.xaml", UriKind.Absolute),
            });
            App.DispatcherUnhandledException += (s, e) =>
            {
                Log.Error("window error", e.Exception);
                e.Handled = true;
                ExitCode = 1;
                App.Shutdown(1);
            };
        }

        public static int Run()
        {
            App.Run();
            return ExitCode;
        }

        /// <summary>Call from a window's Closed handler.</summary>
        public static void WindowClosed()
        {
            if (App.Windows.Count == 0) App.Shutdown(ExitCode);
        }

        public static void OnUi(Action act) =>
            App.Dispatcher.BeginInvoke(DispatcherPriority.Normal, act);

        public static async Task WaitForWindow(Process app, int timeoutMs)
        {
            if (app == null) return;
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < timeoutMs)
            {
                try
                {
                    if (app.HasExited) return;
                }
                catch
                {
                    return;
                }
                if (Launcher.WindowOf(app.Id) != IntPtr.Zero) return;
                await Task.Delay(150);
            }
        }

        public static string StepText(Step step)
        {
            switch (step)
            {
                case Step.Preparing: return S.StepPreparing;
                case Step.Copying: return S.StepCopying;
                case Step.Checking: return S.StepChecking;
                case Step.Closing: return S.StepClosing;
                case Step.Finishing: return S.StepFinishing;
                case Step.Removing: return S.StepRemoving;
                default: return S.StepFinishing;
            }
        }

        public static string Describe(SetupException p)
        {
            switch (p.Problem)
            {
                case Problem.DiskFull:
                {
                    var parts = (p.Detail ?? "").Split('|');
                    long need = 0;
                    if (parts.Length > 1) long.TryParse(parts[1], out need);
                    return S.ProblemDiskFull(parts[0].TrimEnd(':'), S.Megabytes(Math.Max(need, 1 << 20)));
                }
                case Problem.AccessDenied: return S.ProblemAccess;
                case Problem.BadFolder: return S.ProblemBadFolder;
                case Problem.Damaged: return S.ProblemDamaged;
                case Problem.StillRunning: return S.ProblemRunning;
                case Problem.FilesInUse: return S.ProblemInUse;
                default: return S.ProblemGeneric;
            }
        }

        /// <summary>Where the user's music is, for the uninstaller's reassurance.</summary>
        public static string MusicFolder(Env env)
        {
            try
            {
                string settings = Path.Combine(env.DataDir, "settings.json");
                if (File.Exists(settings))
                {
                    string dir = Json.Str(Json.ParseObject(File.ReadAllText(settings)), "download_dir");
                    if (!string.IsNullOrWhiteSpace(dir) && Directory.Exists(dir)) return dir;
                }
            }
            catch
            {
                // fall through to the default
            }
            string fallback = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyMusic), "Dannify");
            return Directory.Exists(fallback) ? fallback : null;
        }

        public const string DownloadPage = "https://github.com/DANIELMWENDWA9451/Dannify/releases";

        public static void OpenDownloadPage()
        {
            try
            {
                Process.Start(new ProcessStartInfo(DownloadPage) { UseShellExecute = true })?.Dispose();
            }
            catch (Exception ex)
            {
                Log.Warn("could not open the download page: " + ex.Message);
            }
        }
    }

    /// <summary>
    /// Only one setup at a time. Dannify 3.18 starts a downloaded setup twice
    /// when "Restart to update" is pressed (once as asked, once more on its
    /// way out), so the second waits for the first, then finds nothing to do.
    /// </summary>
    internal sealed class SetupGate : IDisposable
    {
        private readonly Mutex _mutex;
        private bool _owned;

        public SetupGate(Env env)
        {
            _mutex = new Mutex(false, @"Local\DannifySetup" + env.Instance);
        }

        /// <summary>True straight away, or once another setup finishes (false if it never does).</summary>
        public bool Enter(int timeoutMs)
        {
            try
            {
                _owned = _mutex.WaitOne(timeoutMs);
            }
            catch (AbandonedMutexException)
            {
                _owned = true;
            }
            return _owned;
        }

        public void Dispose()
        {
            if (_owned)
            {
                try
                {
                    _mutex.ReleaseMutex();
                }
                catch
                {
                    // released already
                }
            }
            _mutex.Dispose();
        }
    }

    // ------------------------------------------------------------------------
    // Installing with the full window
    // ------------------------------------------------------------------------

    internal sealed class SetupFlow
    {
        private readonly Args _args;
        private readonly Env _env;
        private readonly Payload _payload;
        private SetupWindow _w;
        private Existing _existing;
        private string _root;
        private bool _desktop;
        private bool _launch;
        private bool _busy;
        private bool _committed;
        private CancellationTokenSource _cts;
        private Action _welcomePrimary, _welcomeSecondary, _resultPrimary, _resultSecondary;

        public SetupFlow(Args args, Env env, Payload payload)
        {
            _args = args;
            _env = env;
            _payload = payload;
        }

        public void Show(SetupException startWith = null)
        {
            _existing = Existing.Find(_env, _args.Root);
            _root = _args.Root != null
                ? Path.GetFullPath(_args.Root)
                : (_existing.IsInstalled && _existing.Kind != InstallKind.LegacyMachine ? _existing.Root : Env.DefaultRoot);
            bool keeps = _existing.IsInstalled && _existing.Kind != InstallKind.LegacyMachine;
            _desktop = _args.DesktopShortcut ?? (keeps ? _existing.HasDesktopShortcut : true);
            _launch = _args.Launch ?? true;

            _w = new SetupWindow();
            _w.Title = S.WindowSetup;
            _w.Footer.Text = S.Version(_payload.Version);
            _w.CloseRequested = OnClose;
            _w.Closed += (s, e) => Ui.WindowClosed();
            _w.WelcomePrimary.Click += (s, e) => _welcomePrimary?.Invoke();
            _w.WelcomeSecondary.Click += (s, e) => _welcomeSecondary?.Invoke();
            _w.ResultPrimary.Click += (s, e) => _resultPrimary?.Invoke();
            _w.ResultSecondary.Click += (s, e) => _resultSecondary?.Invoke();
            _w.ProgressCancel.Click += (s, e) => AskToStop();
            _w.LocationChange.Click += (s, e) => ChangeLocation();
            _w.OptDesktop.Checked += (s, e) => _desktop = true;
            _w.OptDesktop.Unchecked += (s, e) => _desktop = false;
            _w.OptLaunch.Checked += (s, e) => _launch = true;
            _w.OptLaunch.Unchecked += (s, e) => _launch = false;
            _w.SheetPrimary.Click += (s, e) => _w.CloseSheet(Begin);

            if (startWith != null) ShowError(startWith);
            else ShowWelcome();
            _w.Show();
            _w.Activate();
        }

        private bool IsUpdate =>
            (_existing.Kind == InstallKind.Current || _existing.Kind == InstallKind.Legacy) &&
            Existing.Compare(_payload.Version, _existing.Version) > 0;

        private void ShowWelcome()
        {
            _w.SetHero(HeroState.Logo);
            _w.WelcomeNote.Visibility = Visibility.Collapsed;
            _w.WelcomeSecondary.Visibility = Visibility.Visible;
            bool installed = _existing.IsInstalled && _existing.Kind != InstallKind.LegacyMachine;
            int compare = installed ? Existing.Compare(_payload.Version, _existing.Version) : 1;

            if (!installed)
            {
                _w.WelcomeText.Text = S.Tagline;
                Welcome(S.Install, Begin, S.Options, OpenOptions);
            }
            else if (compare > 0)
            {
                _w.WelcomeText.Text = S.UpdateFrom(_existing.Version, _payload.Version);
                _w.WelcomeNote.Text = S.KeptNote;
                _w.WelcomeNote.Visibility = Visibility.Visible;
                Welcome(S.Update, Begin, S.Options, OpenOptions);
            }
            else if (compare == 0)
            {
                _w.WelcomeText.Text = S.AlreadyInstalled(_existing.Version ?? _payload.Version);
                Welcome(S.Open, OpenAppAndClose, S.Reinstall, Begin);
            }
            else
            {
                _w.WelcomeText.Text = S.NewerInstalled(_existing.Version);
                Welcome(S.Open, OpenAppAndClose, null, null);
                _w.WelcomeSecondary.Visibility = Visibility.Collapsed;
            }
            _w.ShowPage(_w.WelcomePage);
        }

        private void Welcome(string primary, Action onPrimary, string secondary, Action onSecondary)
        {
            _w.WelcomePrimary.Content = primary;
            _welcomePrimary = onPrimary;
            _w.WelcomeSecondary.Content = secondary;
            _welcomeSecondary = onSecondary;
        }

        private void OpenOptions()
        {
            bool installed = _existing.IsInstalled && _existing.Kind != InstallKind.LegacyMachine;
            _w.SheetTitle.Text = S.Options;
            _w.LocationLabel.Text = S.Location;
            _w.LocationText.Text = Visuals.MiddleTrim(_root, 58);
            _w.LocationText.ToolTip = _root;
            _w.LocationChange.Content = S.Change;
            _w.LocationChange.IsEnabled = !installed && _args.Root == null;
            _w.LocationNote.Text = installed ? S.LocationLocked : "";
            _w.LocationNote.Visibility = installed ? Visibility.Visible : Visibility.Collapsed;
            _w.OptDesktop.Content = S.DesktopShortcut;
            _w.OptDesktop.IsChecked = _desktop;
            _w.OptLaunch.Content = S.OpenWhenDone;
            _w.OptLaunch.IsChecked = _launch;
            _w.SheetPrimary.Content = _w.WelcomePrimary.Content;
            _w.OpenSheet();
        }

        private void ChangeLocation()
        {
            string picked = FolderPicker.Pick(_w, S.PickFolder, _root);
            if (string.IsNullOrEmpty(picked)) return;
            // Picking a folder means "put Dannify in here": it gets its own
            // folder inside, unless the one picked is already called Dannify.
            string root = string.Equals(Path.GetFileName(picked.TrimEnd('\\')), "Dannify", StringComparison.OrdinalIgnoreCase)
                ? picked
                : Path.Combine(picked, "Dannify");
            string problem = null;
            if (Engine.IsUnsuitable(root, _env)) problem = S.ProblemBadFolder;
            else if (!CanWrite(root)) problem = S.ProblemAccess;
            if (problem != null)
            {
                _w.LocationNote.Text = problem;
                _w.LocationNote.Visibility = Visibility.Visible;
                return;
            }
            _root = Path.GetFullPath(root).TrimEnd('\\');
            _w.LocationNote.Visibility = Visibility.Collapsed;
            _w.LocationText.Text = Visuals.MiddleTrim(_root, 58);
            _w.LocationText.ToolTip = _root;
        }

        private static bool CanWrite(string root)
        {
            try
            {
                string probeDir = root;
                while (!Directory.Exists(probeDir))
                {
                    string parent = Path.GetDirectoryName(probeDir);
                    if (string.IsNullOrEmpty(parent)) return false;
                    probeDir = parent;
                }
                string probe = Path.Combine(probeDir, ".dannify-write-test-" + Guid.NewGuid().ToString("N").Substring(0, 6));
                File.WriteAllText(probe, "");
                File.Delete(probe);
                return true;
            }
            catch
            {
                return false;
            }
        }

        private async void Begin()
        {
            if (_busy) return;
            _busy = true;
            _committed = false;
            bool update = IsUpdate;
            _w.ProgressTitle.Text = update ? S.Updating : S.Installing;
            _w.ProgressCancel.Content = S.Cancel;
            _w.ProgressCancel.Visibility = Visibility.Visible;
            _w.ProgressCancel.IsEnabled = true;
            _w.ResetProgress();
            _w.SetHero(HeroState.Logo);
            _w.SetProgress(0, S.StepPreparing);
            _w.ShowPage(_w.ProgressPage);

            _cts = new CancellationTokenSource();
            var plan = new InstallPlan
            {
                Root = _root,
                DesktopShortcut = _desktop,
                MayForceClose = false,
                AskToForce = AskToForce,
            };
            var engine = new Engine(_env)
            {
                OnProgress = (step, f) => Ui.OnUi(() => OnProgress(step, f)),
            };

            Exception failure = null;
            try
            {
                await Task.Run(() =>
                {
                    using (var gate = new SetupGate(_env))
                    {
                        if (!gate.Enter(10 * 60 * 1000)) throw new SetupException(Problem.Generic, "another setup never finished");
                        engine.Install(_payload, _existing, plan, _cts.Token);
                    }
                });
            }
            catch (Exception ex)
            {
                failure = ex;
            }
            _busy = false;
            _w.CloseLocked = false;

            if (failure == null)
            {
                if (_existing.Kind == InstallKind.LegacyMachine) await RemoveMachineCopy();
                await Finish(update);
                return;
            }
            var problem = SetupException.From(failure);
            if (problem.Problem == Problem.Cancelled)
            {
                _existing = Existing.Find(_env, _args.Root);
                ShowWelcome();
                return;
            }
            Log.Error("install failed", failure);
            ShowError(problem);
        }

        private void OnProgress(Step step, double fraction)
        {
            if (step >= Step.Closing && _w.ProgressCancel.Visibility == Visibility.Visible)
                Visuals.Leave(_w.ProgressCancel);
            if (step >= Step.Finishing && !_committed)
            {
                _committed = true;
                _w.CloseLocked = true;
            }
            _w.SetProgress(fraction, Ui.StepText(step));
        }

        private bool AskToForce()
        {
            // Called from the install thread: ask on the window's thread and wait.
            var answer = Ui.App.Dispatcher.Invoke(() => _w.Ask(S.StillOpenTitle, S.StillOpenText, S.CloseIt, S.Cancel));
            return answer.Result;
        }

        private async void AskToStop()
        {
            if (!_busy || _committed) return;
            // An update being stopped leaves the version that is there; saying
            // "stop installing" over it read as if nothing would be left.
            bool stop = IsUpdate
                ? await _w.Ask(S.StopUpdateTitle, S.StopUpdateText, S.Stop, S.KeepGoing)
                : await _w.Ask(S.StopTitle, S.StopText, S.Stop, S.KeepGoing);
            if (stop && !_committed)
            {
                _w.ProgressCancel.IsEnabled = false;
                _cts?.Cancel();
            }
        }

        private async Task RemoveMachineCopy()
        {
            _w.SetWaiting(S.MachineCopy);
            try
            {
                var psi = new ProcessStartInfo(Env.SelfPath, "--remove-machine-copy \"" + _existing.Root + "\"")
                {
                    UseShellExecute = true,
                    Verb = "runas",
                };
                using (var p = Process.Start(psi))
                    if (p != null) await Task.Run(() => p.WaitForExit(120000));
            }
            catch (Exception ex)
            {
                // Declined at the prompt, most likely. Both copies keep working.
                Log.Warn("left the copy for all users in place: " + ex.Message);
            }
        }

        private async Task Finish(bool update)
        {
            _w.ProgressDone();
            _w.SetHero(HeroState.Check);
            _w.ResultTitle.Text = S.ReadyTitle;
            _w.ResultText.Text = update ? S.UpdatedTo(_payload.Version) : S.InstalledVersion(_payload.Version);
            if (_launch)
            {
                _w.ResultPrimary.Visibility = Visibility.Collapsed;
                _w.ResultSecondary.Visibility = Visibility.Collapsed;
                _w.ShowPage(_w.ResultPage);
                await Task.Delay(Visuals.Motion ? 1100 : 300);
                _w.ResultText.Text = S.Opening;
                Process app = null;
                try
                {
                    app = Launcher.Start(_env, Enumerable.Empty<string>());
                }
                catch (Exception ex)
                {
                    Log.Error("could not open Dannify", ex);
                }
                await Ui.WaitForWindow(app, 25000);
                _w.CloseNow();
                return;
            }
            _w.ResultPrimary.Visibility = Visibility.Visible;
            _w.ResultPrimary.Content = S.Open;
            _resultPrimary = OpenAppAndClose;
            _w.ResultSecondary.Visibility = Visibility.Visible;
            _w.ResultSecondary.Content = S.Close;
            _resultSecondary = _w.CloseNow;
            _w.ShowPage(_w.ResultPage);
        }

        private async void OpenAppAndClose()
        {
            _w.WelcomePrimary.IsEnabled = false;
            _w.ResultPrimary.IsEnabled = false;
            try
            {
                if (_existing.Root != null && _env.Root == null) _env.Root = _existing.Root;
                if (_env.Root == null) _env.Root = _root;
                var app = Launcher.Start(_env, Enumerable.Empty<string>());
                await Ui.WaitForWindow(app, 20000);
            }
            catch (Exception ex)
            {
                Log.Error("could not open Dannify", ex);
            }
            _w.CloseNow();
        }

        private void ShowError(SetupException problem)
        {
            _w.SetHero(HeroState.Warn);
            _w.ResultTitle.Text = IsUpdate ? S.FailedUpdate : S.FailedInstall;
            _w.ResultText.Text = Ui.Describe(problem);
            _w.ResultPrimary.IsEnabled = true;
            _w.ResultPrimary.Visibility = Visibility.Visible;
            _w.ResultSecondary.Visibility = Visibility.Visible;
            _w.ResultSecondary.Content = S.Close;
            _resultSecondary = _w.CloseNow;
            if (problem.Problem == Problem.Damaged)
            {
                _w.ResultPrimary.Content = S.Download;
                _resultPrimary = () =>
                {
                    Ui.OpenDownloadPage();
                    _w.CloseNow();
                };
            }
            else if (problem.Problem == Problem.AccessDenied || problem.Problem == Problem.BadFolder)
            {
                _w.ResultPrimary.Content = S.Options;
                _resultPrimary = () =>
                {
                    ShowWelcome();
                    OpenOptions();
                };
            }
            else
            {
                _w.ResultPrimary.Content = S.TryAgain;
                _resultPrimary = Begin;
            }
            _w.ShowPage(_w.ResultPage);
        }

        private void OnClose()
        {
            if (_busy)
            {
                if (!_committed) AskToStop();
                return;
            }
            _w.CloseNow();
        }
    }

    // ------------------------------------------------------------------------
    // Updating from inside the app: a small window, no questions
    // ------------------------------------------------------------------------

    internal sealed class UpdateFlow
    {
        private readonly Args _args;
        private readonly Env _env;
        private readonly Payload _payload;
        private SplashWindow _s;

        public UpdateFlow(Args args, Env env, Payload payload)
        {
            _args = args;
            _env = env;
            _payload = payload;
        }

        public void Show()
        {
            var existing = Existing.Find(_env, _args.Root);
            bool installed = existing.IsInstalled && existing.Kind != InstallKind.LegacyMachine;
            _s = new SplashWindow();
            _s.Title = installed ? S.WindowUpdating : S.WindowSetup;
            _s.SetHeading(installed ? S.Updating : S.Installing);
            _s.SetProgress(0, S.StepPreparing);
            _s.Closed += (o, e) => Ui.WindowClosed();
            _s.Show();
            Run(existing);
        }

        private async void Run(Existing existing)
        {
            bool launch = _args.Launch ?? true;
            string root = _args.Root != null
                ? Path.GetFullPath(_args.Root)
                : (existing.IsInstalled && existing.Kind != InstallKind.LegacyMachine ? existing.Root : Env.DefaultRoot);
            var plan = new InstallPlan
            {
                Root = root,
                DesktopShortcut = _args.DesktopShortcut ?? (existing.IsInstalled ? existing.HasDesktopShortcut : true),
                MayForceClose = true,
            };
            var engine = new Engine(_env)
            {
                OnProgress = (step, f) => Ui.OnUi(() => _s.SetProgress(f, Ui.StepText(step))),
            };

            Exception failure = null;
            bool nothingToDo = false;
            try
            {
                await Task.Run(() =>
                {
                    using (var gate = new SetupGate(_env))
                    {
                        if (!gate.Enter(0))
                        {
                            Ui.OnUi(() => _s.SetWaiting(S.JustAMoment));
                            if (!gate.Enter(10 * 60 * 1000)) throw new SetupException(Problem.Generic, "another setup never finished");
                            // It may well have installed this very version.
                            var now = Existing.Find(_env, _args.Root);
                            if (now.Kind == InstallKind.Current && Existing.Compare(_payload.Version, now.Version) <= 0)
                            {
                                nothingToDo = true;
                                _env.Root = now.Root;
                                return;
                            }
                            existing = now;
                        }
                        engine.Install(_payload, existing, plan, CancellationToken.None);
                    }
                });
            }
            catch (Exception ex)
            {
                failure = ex;
            }

            if (failure != null)
            {
                Log.Error("update failed", failure);
                try
                {
                    // Say what went wrong in the full window, which can also retry.
                    new SetupFlow(_args, _env, _payload).Show(SetupException.From(failure));
                }
                catch (Exception ex)
                {
                    Log.Error("could not show the problem", ex);
                }
                _s.CloseNow();
                return;
            }

            try
            {
                _s.SetProgress(1, nothingToDo ? S.JustAMoment : S.StepFinishing);
                if (launch)
                {
                    _s.SetHeading(S.Opening);
                    if (_env.Root == null) _env.Root = root;
                    var app = Launcher.Start(_env, Enumerable.Empty<string>());
                    await Ui.WaitForWindow(app, 25000);
                }
            }
            catch (Exception ex)
            {
                Log.Error("could not open Dannify", ex);
            }
            finally
            {
                _s.CloseNow();
            }
        }
    }

    // ------------------------------------------------------------------------
    // Restart to update: close, swap, open, with a small window in between
    // ------------------------------------------------------------------------

    internal sealed class RestartFlow
    {
        private readonly Args _args;
        private readonly Env _env;
        private SplashWindow _s;

        public RestartFlow(Args args, Env env)
        {
            _args = args;
            _env = env;
        }

        public void Show()
        {
            bool pending = Launcher.HasPending(_env);
            _s = new SplashWindow();
            _s.Title = pending ? S.WindowUpdating : "Dannify";
            _s.SetHeading(pending ? S.Updating : S.Restarting);
            _s.SetWaiting(S.JustAMoment);
            IntPtr old = Launcher.WindowOf(_args.AfterPid, 300);
            if (old != IntPtr.Zero && Native.GetWindowRect(old, out var rect)) _s.PlaceOver(rect);
            _s.Closed += (o, e) => Ui.WindowClosed();
            _s.Show();
            Run();
        }

        private async void Run()
        {
            try
            {
                bool swapped = false;
                await Task.Run(() =>
                {
                    if (!Apps.WaitForExit(_args.AfterPid, 30000))
                    {
                        Apps.RequestQuit(_env.QuitEventName);
                        if (!Apps.WaitForExit(_args.AfterPid, 10000)) Apps.Kill(new[] { _args.AfterPid });
                    }
                    Apps.WaitUntil(() => !Launcher.AppRunning(_env), 15000, CancellationToken.None);
                    swapped = Launcher.TryApplyPending(_env, 10000);
                });

                Process app = await Task.Run(() => LaunchCare.StartWatched(_env, _args.PassThrough, swapped));
                await Ui.WaitForWindow(app, 20000);
            }
            catch (Exception ex)
            {
                Log.Error("restart", ex);
            }
            finally
            {
                _s.CloseNow();
            }
        }
    }

    // ------------------------------------------------------------------------
    // Removing
    // ------------------------------------------------------------------------

    internal sealed class UninstallFlow
    {
        private readonly Env _env;
        private SetupWindow _w;
        private string _music;
        private bool _busy;
        private Action _resultPrimary, _resultSecondary;

        public UninstallFlow(Env env)
        {
            _env = env;
        }

        public void Show()
        {
            _music = Ui.MusicFolder(_env);
            _w = new SetupWindow();
            _w.Title = S.WindowRemove;
            string version = Existing.FileVersion(_env.AppExe) ?? Registration.ReadCurrent(_env).version;
            _w.Footer.Text = version == null ? "" : S.Version(version);
            _w.Closed += (s, e) => Ui.WindowClosed();
            _w.CloseRequested = () =>
            {
                if (!_busy) _w.CloseNow();
            };
            _w.RemoveTitle.Text = S.RemoveTitle;
            _w.RemoveText.Text = _music != null ? S.MusicStays(Visuals.MiddleTrim(_music, 56)) : S.MusicStaysGeneric;
            _w.RemoveSettings.Content = S.AlsoSettings;
            _w.RemoveSettings.ToolTip = S.SignInGoes;
            _w.RemoveSettings.IsChecked = false;
            _w.RemovePrimary.Content = S.Remove;
            _w.RemovePrimary.Click += (s, e) => Begin();
            _w.RemoveCancel.Content = S.Cancel;
            _w.RemoveCancel.Click += (s, e) => _w.CloseNow();
            _w.ResultPrimary.Click += (s, e) => _resultPrimary?.Invoke();
            _w.ResultSecondary.Click += (s, e) => _resultSecondary?.Invoke();
            _w.SetHero(HeroState.Logo);
            _w.ShowPage(_w.RemovePage);
            _w.Show();
            _w.Activate();
        }

        private async void Begin()
        {
            if (_busy) return;
            _busy = true;
            bool removeSettings = _w.RemoveSettings.IsChecked == true;
            _w.ProgressTitle.Text = S.Removing;
            _w.ProgressCancel.Visibility = Visibility.Collapsed;
            _w.ResetProgress();
            _w.SetProgress(0.02, S.StepClosing);
            _w.ShowPage(_w.ProgressPage);
            _w.CloseLocked = true;

            var engine = new Engine(_env)
            {
                OnProgress = (step, f) => Ui.OnUi(() => _w.SetProgress(f, Ui.StepText(step))),
            };
            Exception failure = null;
            try
            {
                await Task.Run(() => engine.Uninstall(removeSettings, false, AskToForce, CancellationToken.None));
            }
            catch (Exception ex)
            {
                failure = ex;
            }
            _busy = false;
            _w.CloseLocked = false;
            _w.ProgressDone();

            _w.ResultPrimary.Visibility = Visibility.Visible;
            if (failure == null)
            {
                _w.SetHero(HeroState.Check);
                _w.ResultTitle.Text = S.RemovedTitle;
                _w.ResultText.Text = _music != null ? S.MusicStill(Visuals.MiddleTrim(_music, 56)) : S.MusicStillGeneric;
                _w.ResultPrimary.Content = S.Close;
                _resultPrimary = _w.CloseNow;
                _w.ResultSecondary.Visibility = Visibility.Collapsed;
            }
            else
            {
                Log.Error("uninstall failed", failure);
                var problem = SetupException.From(failure);
                _w.SetHero(HeroState.Warn);
                _w.ResultTitle.Text = S.FailedRemove;
                _w.ResultText.Text = problem.Problem == Problem.StillRunning ? S.ProblemRunning : S.ProblemGenericRemove;
                _w.ResultPrimary.Content = S.TryAgain;
                _resultPrimary = Begin;
                _w.ResultSecondary.Visibility = Visibility.Visible;
                _w.ResultSecondary.Content = S.Close;
                _resultSecondary = _w.CloseNow;
            }
            _w.ShowPage(_w.ResultPage);
        }

        private bool AskToForce()
        {
            var answer = Ui.App.Dispatcher.Invoke(() => _w.Ask(S.StillOpenTitle, S.StillOpenText, S.CloseIt, S.Cancel));
            return answer.Result;
        }
    }

    // ------------------------------------------------------------------------
    // Something is wrong with this copy
    // ------------------------------------------------------------------------

    internal static class Messages
    {
        /// <summary>The launcher found no app to start, and nothing to bring back.</summary>
        public static void Broken() => Show(S.BrokenTitle, S.BrokenText);

        /// <summary>A setup file that lost its end on the way down.</summary>
        public static void Damaged() => Show(S.FailedInstall, S.ProblemDamaged);

        private static void Show(string title, string text)
        {
            var w = new SetupWindow();
            w.Closed += (s, e) => Ui.WindowClosed();
            w.SetHero(HeroState.Warn);
            w.ResultTitle.Text = title;
            w.ResultText.Text = text;
            w.ResultPrimary.Content = S.Download;
            w.ResultPrimary.Click += (s, e) =>
            {
                Ui.OpenDownloadPage();
                w.CloseNow();
            };
            w.ResultSecondary.Content = S.Close;
            w.ResultSecondary.Click += (s, e) => w.CloseNow();
            w.ShowPage(w.ResultPage);
            w.Show();
            w.Activate();
        }
    }
}
