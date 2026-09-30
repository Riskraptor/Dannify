using System.Globalization;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// Every word the installer shows, in English and French (the two
    /// languages the app itself ships). French follows the Windows display
    /// language; --lang fr|en overrides it.
    /// </summary>
    internal static class S
    {
        public static bool French { get; private set; }

        public static void Init(string lang)
        {
            string code = string.IsNullOrWhiteSpace(lang)
                ? CultureInfo.CurrentUICulture.TwoLetterISOLanguageName
                : lang.Trim().ToLowerInvariant();
            French = code.StartsWith("fr");
        }

        private static string T(string en, string fr) => French ? fr : en;

        // Nbsp before French high punctuation, as French typography wants.
        private const string Nb = " ";

        public static string AppName => "Dannify";
        public static string Tagline => T("Stream and save the music you love.", "Écoutez et gardez la musique que vous aimez.");
        public static string Version(string v) => T("Version ", "Version ") + v;

        public static string Install => T("Install", "Installer");
        public static string Update => T("Update", "Mettre à jour");
        public static string Reinstall => T("Reinstall", "Réinstaller");
        public static string Open => T("Open Dannify", "Ouvrir Dannify");
        public static string Close => T("Close", "Fermer");
        public static string Cancel => T("Cancel", "Annuler");
        public static string Back => T("Back", "Retour");
        public static string Options => T("Options", "Options");
        public static string TryAgain => T("Try again", "Réessayer");
        public static string Minimize => T("Minimize", "Réduire");

        public static string UpdateFrom(string from, string to) =>
            from == null
                ? T("Update to version " + to + ".", "Mise à jour vers la version " + to + ".")
                : T("Update from " + from + " to " + to + ".", "Mise à jour de la " + from + " vers la " + to + ".");
        public static string KeptNote => T("Your music and settings stay as they are.", "Votre musique et vos réglages restent tels quels.");
        public static string AlreadyInstalled(string v) => T("Version " + v + " is already installed.", "La version " + v + " est déjà installée.");
        public static string NewerInstalled(string v) => T("A newer version (" + v + ") is already installed.", "Une version plus récente (" + v + ") est déjà installée.");

        public static string Location => T("Install location", "Emplacement");
        public static string Change => T("Change", "Modifier");
        public static string DesktopShortcut => T("Add a shortcut to the desktop", "Ajouter un raccourci sur le Bureau");
        public static string OpenWhenDone => T("Open Dannify when setup finishes", "Ouvrir Dannify à la fin");
        public static string PickFolder => T("Choose where to install Dannify", "Choisissez où installer Dannify");
        public static string LocationLocked => T("To move Dannify, remove it first, then install it again.", "Pour déplacer Dannify, supprimez-le d'abord, puis réinstallez-le.");

        public static string Installing => T("Installing Dannify", "Installation de Dannify");
        public static string Updating => T("Updating Dannify", "Mise à jour de Dannify");
        public static string Removing => T("Removing Dannify", "Suppression de Dannify");
        public static string Restarting => T("Restarting Dannify", "Redémarrage de Dannify");
        public static string StepPreparing => T("Getting ready", "Préparation");
        public static string StepCopying => T("Copying files", "Copie des fichiers");
        public static string StepChecking => T("Checking files", "Vérification des fichiers");
        public static string StepClosing => T("Closing Dannify", "Fermeture de Dannify");
        public static string StepFinishing => T("Finishing up", "Finalisation");
        public static string StepRemoving => T("Removing files", "Suppression des fichiers");
        public static string JustAMoment => T("Just a moment", "Un instant");

        public static string StopTitle => T("Stop installing?", "Arrêter l'installation" + Nb + "?");
        public static string StopText => T("Nothing will be changed on your PC.", "Rien ne sera modifié sur votre PC.");
        public static string StopUpdateTitle => T("Stop updating?", "Arrêter la mise à jour" + Nb + "?");
        public static string StopUpdateText => T("Dannify stays on the version you have now.", "Dannify reste sur la version actuelle.");

        // What the taskbar and Alt+Tab call these windows. They were all
        // "Dannify", next to the app's own window of the same name.
        public static string WindowSetup => T("Dannify Setup", "Installation de Dannify");
        public static string WindowRemove => T("Remove Dannify", "Supprimer Dannify");
        public static string WindowUpdating => T("Updating Dannify", "Mise à jour de Dannify");
        public static string Stop => T("Stop", "Arrêter");
        public static string KeepGoing => T("Keep going", "Continuer");

        public static string ReadyTitle => T("Dannify is ready", "Dannify est prêt");
        public static string UpdatedTo(string v) => T("Updated to version " + v + ".", "Mis à jour vers la version " + v + ".");
        public static string InstalledVersion(string v) => T("Version " + v + " is installed.", "La version " + v + " est installée.");
        public static string Opening => T("Opening Dannify", "Ouverture de Dannify");

        public static string FailedInstall => T("Dannify couldn't be installed", "Impossible d'installer Dannify");
        public static string FailedUpdate => T("Dannify couldn't be updated", "Impossible de mettre à jour Dannify");
        public static string FailedRemove => T("Dannify couldn't be removed", "Impossible de supprimer Dannify");
        public static string ProblemDiskFull(string drive, string amount) =>
            T("There isn't enough free space on drive " + drive + ". Free up " + amount + " and try again.",
              "Il n'y a pas assez d'espace libre sur le lecteur " + drive + ". Libérez " + amount + " et réessayez.");
        public static string ProblemAccess => T("Dannify isn't allowed to write to that folder. Choose another one in Options.",
            "Dannify n'a pas le droit d'écrire dans ce dossier. Choisissez-en un autre dans Options.");
        public static string ProblemBadFolder => T("Dannify can't be installed in that folder. Choose another one in Options.",
            "Dannify ne peut pas être installé dans ce dossier. Choisissez-en un autre dans Options.");
        public static string ProblemDamaged => T("This setup file is damaged. Download Dannify again.",
            "Ce fichier d'installation est endommagé. Téléchargez Dannify à nouveau.");
        public static string ProblemRunning => T("Dannify is still open. Close it, then try again.",
            "Dannify est encore ouvert. Fermez-le, puis réessayez.");
        public static string ProblemInUse => T("Another program is using Dannify's files. Restart your PC, then try again.",
            "Un autre programme utilise les fichiers de Dannify. Redémarrez votre PC, puis réessayez.");
        public static string ProblemGeneric => T("Something went wrong. Nothing was changed on your PC.",
            "Un problème est survenu. Rien n'a été modifié sur votre PC.");
        public static string ProblemGenericRemove => T("Something went wrong. Try again in a moment.",
            "Un problème est survenu. Réessayez dans un instant.");

        public static string StillOpenTitle => T("Dannify is still open", "Dannify est encore ouvert");
        public static string StillOpenText => T("It didn't close when asked. Close it now to continue?",
            "Il ne s'est pas fermé. Le fermer maintenant pour continuer" + Nb + "?");
        public static string CloseIt => T("Close Dannify", "Fermer Dannify");

        public static string RemoveTitle => T("Remove Dannify?", "Supprimer Dannify" + Nb + "?");
        public static string MusicStays(string folder) => T("Your music stays in " + folder + ".", "Votre musique reste dans " + folder + ".");
        public static string MusicStaysGeneric => T("Your music stays where it is.", "Votre musique reste où elle est.");
        public static string AlsoSettings => T("Also remove my settings", "Supprimer aussi mes réglages");
        public static string SignInGoes => T("Your sign-in is removed either way: sign in again after reinstalling.",
            "Votre connexion est supprimée dans tous les cas : reconnectez-vous après une réinstallation.");
        public static string Remove => T("Remove", "Supprimer");
        public static string RemovedTitle => T("Dannify was removed", "Dannify a été supprimé");
        public static string MusicStill(string folder) => T("Your music is still in " + folder + ".", "Votre musique est toujours dans " + folder + ".");
        public static string MusicStillGeneric => T("Your music is still on this PC.", "Votre musique est toujours sur ce PC.");

        public static string BrokenTitle => T("Dannify needs to be reinstalled", "Dannify doit être réinstallé");
        public static string BrokenText => T("Some of its files are missing. Download Dannify again to fix it.",
            "Certains de ses fichiers sont manquants. Téléchargez Dannify à nouveau pour le réparer.");
        public static string Download => T("Download Dannify", "Télécharger Dannify");

        public static string MachineCopy => T("Removing the copy installed for all users", "Suppression de la copie installée pour tous les utilisateurs");

        public static string Megabytes(long bytes)
        {
            double mb = bytes / 1048576.0;
            return mb >= 1024
                ? (mb / 1024).ToString(mb >= 10240 ? "0" : "0.0", French ? CultureInfo.GetCultureInfo("fr-FR") : CultureInfo.InvariantCulture) + T(" GB", " Go")
                : System.Math.Ceiling(mb).ToString("0", CultureInfo.InvariantCulture) + T(" MB", " Mo");
        }
    }
}
