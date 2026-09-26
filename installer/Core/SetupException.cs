using System;
using System.IO;

namespace Dannify.Setup.Core
{
    internal enum Problem
    {
        Generic,
        DiskFull,
        AccessDenied,
        Damaged,
        StillRunning,
        FilesInUse,
        Cancelled,
        NotInstalled,
        BadFolder,
    }

    /// <summary>A failure with a reason the window can put into words.</summary>
    internal sealed class SetupException : Exception
    {
        public Problem Problem { get; }
        public string Detail { get; }

        public SetupException(Problem problem, string detail = null, Exception inner = null)
            : base(problem + (detail == null ? "" : ": " + detail), inner)
        {
            Problem = problem;
            Detail = detail;
        }

        /// <summary>Sort an arbitrary failure into one of the reasons above.</summary>
        public static SetupException From(Exception ex)
        {
            switch (ex)
            {
                case SetupException known:
                    return known;
                case OperationCanceledException _:
                    return new SetupException(Problem.Cancelled, null, ex);
                case UnauthorizedAccessException _:
                    return new SetupException(Problem.AccessDenied, null, ex);
                case InvalidDataException _:
                    return new SetupException(Problem.Damaged, null, ex);
                case IOException io:
                    int code = io.HResult & 0xFFFF;
                    if (code == 0x70 || code == 0x27) return new SetupException(Problem.DiskFull, null, ex);
                    if (code == 0x20 || code == 0x21) return new SetupException(Problem.FilesInUse, null, ex);
                    if (code == 0x05) return new SetupException(Problem.AccessDenied, null, ex);
                    return new SetupException(Problem.Generic, null, ex);
                case AggregateException agg when agg.InnerExceptions.Count > 0:
                    return From(agg.Flatten().InnerExceptions[0]);
                default:
                    return new SetupException(Problem.Generic, null, ex);
            }
        }
    }
}
