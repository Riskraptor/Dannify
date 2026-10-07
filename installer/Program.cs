using System;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using Dannify.Setup.Core;
using Dannify.Setup.UI;

namespace Dannify.Setup
{
    /// <summary>
    /// One program, four jobs, picked from how it was started:
    ///
    ///   Dannify-Setup-x.y.z.exe            installs or updates (the app is packed on its end)
    ///   &lt;install&gt;\Dannify.exe             starts Dannify, first applying a waiting update
    ///   &lt;install&gt;\Dannify.exe --uninstall  removes it
    ///   &lt;install&gt;\Dannify.exe --after PID  "restart to update": waits, swaps, reopens
    ///
    /// The everyday path (starting the app) touches nothing from WPF, so it
    /// costs a few milliseconds before the app itself is on its way.
    /// </summary>
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] argv)
        {
            Args args;
            try
            {
                args = Args.Parse(argv);
            }
            catch
            {
                args = Args.Parse(new string[0]);
            }

            Payload payload = null;
            bool damaged = false;
            try
            {
                payload = Payload.Open(Env.SelfPath);
            }
            catch (InvalidDataException)
            {
                damaged = true;
            }

            string selfDir = Path.GetDirectoryName(Env.SelfPath);
            bool inPlace = payload == null && !damaged &&
                (string.Equals(Path.GetFileName(Env.SelfPath), Env.ExeName, StringComparison.OrdinalIgnoreCase) ||
                 Directory.Exists(Path.Combine(selfDir, "app")) ||
                 Directory.Exists(Path.Combine(selfDir, "app-next")));
            // A setup file with nothing on its end lost it on the way down.
            if (payload == null && !inPlace && !args.Uninstall && args.RemoveMachineCopy == null && args.UiState == null)
                damaged = true;

            Env env;
            try
            {
                env = Env.Create(args, args.Root ?? (inPlace ? selfDir : null));
            }
            catch (Exception)
            {
                return 2;
            }
            Log.Init(env.DataDir);

            try
            {
                if (args.RemoveMachineCopy != null) return Engine.RemoveMachineCopy(args.RemoveMachineCopy);
                if (args.VerifyPayload) return Verify(payload, null);
                if (args.UnpackTo != null) return Verify(payload, args.UnpackTo);
                if (args.WriteEngineTo != null)
                {
                    if (payload == null) return 4;
                    try
                    {
                        payload.WriteEngine(args.WriteEngineTo);
                        return 0;
                    }
                    catch (Exception ex)
                    {
                        Log.Error("could not write the launcher copy", ex);
                        return 5;
                    }
                }

                if (inPlace && !args.Uninstall && args.AfterPid == 0 && args.UiState == null)
                {
                    if (Launcher.RunQuick(args, env)) return 0;
                    return WithWindow(args.Lang, () => Messages.Broken());
                }

                if (args.Uninstall)
                {
                    if (env.Root == null)
                    {
                        var (root, _) = Registration.ReadCurrent(env);
                        env.Root = root ?? Existing.FromFolder(Env.DefaultRoot)?.Root;
                    }
                    if (env.Root == null) return 3;
                    if (args.Quiet) return UninstallQuietly(env);
                    return WithWindow(args.Lang, () => new UninstallFlow(env).Show());
                }

                if (payload != null && args.Quiet) return InstallQuietly(args, env, payload);

                return WithWindow(args.Lang, () =>
                {
                    if (args.UiState != null) Preview.Show(args, env, payload);
                    else if (args.AfterPid > 0) new RestartFlow(args, env).Show();
                    else if (damaged || payload == null) Messages.Damaged();
                    else if (args.ProgressOnly || FromTheApp(env)) new UpdateFlow(args, env, payload).Show();
                    else new SetupFlow(args, env, payload).Show();
                });
            }
            catch (Exception ex)
            {
                Log.Error("unexpected", ex);
                return 1;
            }
        }

        // Kept out of Main so the everyday launch never loads WPF.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static int WithWindow(string lang, Action open)
        {
            S.Init(lang);
            Ui.Boot();
            // Opened from inside the running message loop, so a flow that
            // starts work straight away is already on the window's thread.
            Ui.App.Dispatcher.BeginInvoke(new Action(() =>
            {
                try
                {
                    open();
                }
                catch (Exception ex)
                {
                    Log.Error("could not open the window", ex);
                    Ui.ExitCode = 1;
                    Ui.App.Shutdown(1);
                }
            }));
            return Ui.Run();
        }

        /// <summary>
        /// A setup the app downloaded for itself: Dannify asked for this update
        /// and is closing so it can happen, so there is nothing to ask.
        /// </summary>
        private static bool FromTheApp(Env env) =>
            Files.IsInside(Env.SelfPath, Path.Combine(env.DataDir, "updates"));

        private static int InstallQuietly(Args args, Env env, Payload payload)
        {
            using (var gate = new SetupGate(env))
            {
                if (!gate.Enter(10 * 60 * 1000)) return 1;
                // Dannify 3.18 starts its setup twice, and the second, quiet
                // one arrives once the first has finished. The same version,
                // or a newer one, already in the folder this run would install
                // to means there is nothing left to do; reinstalling would only
                // close the copy the first run just opened. A named folder is
                // checked as it is: Find looks there and nowhere else.
                var existing = Existing.Find(env, args.Root);
                if (existing.Kind == InstallKind.Current && Existing.Compare(payload.Version, existing.Version) <= 0)
                {
                    Log.Info("quiet setup: " + existing.Version + " is already installed");
                    return 0;
                }
                string root = args.Root != null
                    ? Path.GetFullPath(args.Root)
                    : (existing.IsInstalled && existing.Kind != InstallKind.LegacyMachine ? existing.Root : Env.DefaultRoot);
                try
                {
                    new Engine(env).Install(payload, existing, new InstallPlan
                    {
                        Root = root,
                        DesktopShortcut = args.DesktopShortcut ?? (existing.IsInstalled ? existing.HasDesktopShortcut : true),
                        MayForceClose = true,
                    }, CancellationToken.None);
                }
                catch (Exception ex)
                {
                    Log.Error("quiet setup failed", ex);
                    return 1;
                }
                if (args.Launch == true) Launcher.Start(env, Enumerable.Empty<string>())?.Dispose();
                return 0;
            }
        }

        private static int UninstallQuietly(Env env)
        {
            try
            {
                new Engine(env).Uninstall(false, true, null, CancellationToken.None);
                return 0;
            }
            catch (Exception ex)
            {
                Log.Error("quiet uninstall failed", ex);
                return 1;
            }
        }

        /// <summary>
        /// Build check: unpack everything and hash it against the list. With
        /// <paramref name="into"/> the files are kept there; without, they go
        /// to a temporary folder that is removed afterwards.
        /// </summary>
        private static int Verify(Payload payload, string into)
        {
            if (payload == null) return 4;
            string target = into ?? Path.Combine(Path.GetTempPath(), "dannify-verify-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            try
            {
                payload.VerifyChecksum(CancellationToken.None);
                payload.Extract(target, CancellationToken.None, null);
                payload.VerifyFiles(target, CancellationToken.None, null);
                Log.Info("payload " + payload.Version + " verified: " + payload.Files.Count + " files");
                return 0;
            }
            catch (Exception ex)
            {
                Log.Error("payload verification failed", ex);
                return 5;
            }
            finally
            {
                if (into == null) Files.TryDeleteDir(target);
            }
        }
    }
}
