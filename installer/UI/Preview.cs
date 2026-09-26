using System.Windows;
using Dannify.Setup.Core;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// --ui-state NAME: show one screen with sample content and do nothing
    /// else. For looking at the design without installing anything.
    /// </summary>
    internal static class Preview
    {
        public static void Show(Args args, Env env, Payload payload)
        {
            string v = payload?.Version ?? "4.0.0";
            string state = (args.UiState ?? "welcome").ToLowerInvariant();
            string music = System.IO.Path.Combine(
                System.Environment.GetFolderPath(System.Environment.SpecialFolder.MyMusic), "Dannify");

            if (state == "splash" || state == "restart")
            {
                var s = new SplashWindow();
                s.Closed += (o, e) => Ui.WindowClosed();
                if (state == "restart")
                {
                    s.SetHeading(S.Updating);
                    s.SetWaiting(S.JustAMoment);
                }
                else
                {
                    s.SetHeading(S.Updating);
                    s.SetProgress(0.62, S.StepCopying);
                }
                s.Show();
                return;
            }

            var w = new SetupWindow();
            w.Closed += (o, e) => Ui.WindowClosed();
            w.Footer.Text = S.Version(v);
            switch (state)
            {
                case "update":
                    w.WelcomeText.Text = S.UpdateFrom("3.18.1", v);
                    w.WelcomeNote.Text = S.KeptNote;
                    w.WelcomeNote.Visibility = Visibility.Visible;
                    w.WelcomePrimary.Content = S.Update;
                    w.WelcomeSecondary.Content = S.Options;
                    w.ShowPage(w.WelcomePage);
                    break;
                case "same":
                    w.WelcomeText.Text = S.AlreadyInstalled(v);
                    w.WelcomePrimary.Content = S.Open;
                    w.WelcomeSecondary.Content = S.Reinstall;
                    w.ShowPage(w.WelcomePage);
                    break;
                case "options":
                    w.WelcomeText.Text = S.Tagline;
                    w.WelcomePrimary.Content = S.Install;
                    w.WelcomeSecondary.Content = S.Options;
                    w.ShowPage(w.WelcomePage);
                    w.SheetTitle.Text = S.Options;
                    w.LocationLabel.Text = S.Location;
                    w.LocationText.Text = Visuals.MiddleTrim(Env.DefaultRoot, 58);
                    w.LocationChange.Content = S.Change;
                    w.OptDesktop.Content = S.DesktopShortcut;
                    w.OptDesktop.IsChecked = true;
                    w.OptLaunch.Content = S.OpenWhenDone;
                    w.OptLaunch.IsChecked = true;
                    w.SheetPrimary.Content = S.Install;
                    w.Loaded += (o, e) => w.OpenSheet();
                    break;
                case "progress":
                case "stop":
                    w.ProgressTitle.Text = S.Installing;
                    w.ProgressCancel.Content = S.Cancel;
                    w.SetProgress(0.46, S.StepCopying);
                    w.ShowPage(w.ProgressPage);
                    if (state == "stop") w.Loaded += async (o, e) => await w.Ask(S.StopTitle, S.StopText, S.Stop, S.KeepGoing);
                    break;
                case "done":
                    w.SetHero(HeroState.Check);
                    w.ResultTitle.Text = S.ReadyTitle;
                    w.ResultText.Text = S.InstalledVersion(v);
                    w.ResultPrimary.Content = S.Open;
                    w.ResultSecondary.Content = S.Close;
                    w.ShowPage(w.ResultPage);
                    break;
                case "error":
                    w.SetHero(HeroState.Warn);
                    w.ResultTitle.Text = S.FailedInstall;
                    w.ResultText.Text = S.ProblemDiskFull("C", S.Megabytes(120L * 1048576));
                    w.ResultPrimary.Content = S.TryAgain;
                    w.ResultSecondary.Content = S.Close;
                    w.ShowPage(w.ResultPage);
                    break;
                case "remove":
                    w.RemoveTitle.Text = S.RemoveTitle;
                    w.RemoveText.Text = S.MusicStays(Visuals.MiddleTrim(music, 56));
                    w.RemoveSettings.Content = S.AlsoSettings;
                    w.RemovePrimary.Content = S.Remove;
                    w.RemoveCancel.Content = S.Cancel;
                    w.ShowPage(w.RemovePage);
                    break;
                case "removed":
                    w.SetHero(HeroState.Check);
                    w.ResultTitle.Text = S.RemovedTitle;
                    w.ResultText.Text = S.MusicStill(Visuals.MiddleTrim(music, 56));
                    w.ResultPrimary.Content = S.Close;
                    w.ResultSecondary.Visibility = Visibility.Collapsed;
                    w.ShowPage(w.ResultPage);
                    break;
                case "broken":
                    w.SetHero(HeroState.Warn);
                    w.ResultTitle.Text = S.BrokenTitle;
                    w.ResultText.Text = S.BrokenText;
                    w.ResultPrimary.Content = S.Download;
                    w.ResultSecondary.Content = S.Close;
                    w.ShowPage(w.ResultPage);
                    break;
                default:
                    w.WelcomeText.Text = S.Tagline;
                    w.WelcomePrimary.Content = S.Install;
                    w.WelcomeSecondary.Content = S.Options;
                    w.ShowPage(w.WelcomePage);
                    break;
            }
            w.Show();
        }
    }
}
