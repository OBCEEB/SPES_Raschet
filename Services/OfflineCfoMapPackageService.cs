using System;
using System.Collections.Generic;
using System.IO;

namespace SPES_Raschet.Services
{
    public sealed class OfflinePackageCheckResult
    {
        public bool IsReady => MissingFiles.Count == 0;
        public string PackageRootPath { get; set; } = string.Empty;
        public List<string> MissingFiles { get; } = new List<string>();
    }

    public static class OfflineCfoMapPackageService
    {
        public const string PackageFolder = "MapData\\CFO";
        public const string ManifestFile = "cfo_manifest.json";
        public const string TilesFile = "cfo_map.mbtiles";
        public const string StyleFile = "cfo_style.json";

        public static OfflinePackageCheckResult Validate()
        {
            var result = new OfflinePackageCheckResult();
            var root = ResolvePackageRootPath();
            result.PackageRootPath = root ?? string.Empty;

            if (root == null)
            {
                result.MissingFiles.Add(Path.Combine(PackageFolder, ManifestFile));
                result.MissingFiles.Add(Path.Combine(PackageFolder, TilesFile));
                result.MissingFiles.Add(Path.Combine(PackageFolder, StyleFile));
                return result;
            }

            EnsureFile(root, ManifestFile, result);
            EnsureFile(root, TilesFile, result);
            EnsureFile(root, StyleFile, result);
            return result;
        }

        private static void EnsureFile(string root, string fileName, OfflinePackageCheckResult result)
        {
            var filePath = Path.Combine(root, fileName);
            if (!File.Exists(filePath))
            {
                result.MissingFiles.Add(Path.Combine(PackageFolder, fileName));
            }
        }

        private static string? ResolvePackageRootPath()
        {
            string baseDir = AppContext.BaseDirectory;
            var candidate = Path.Combine(baseDir, PackageFolder);
            if (Directory.Exists(candidate))
                return candidate;

            candidate = Path.Combine(Environment.CurrentDirectory, PackageFolder);
            if (Directory.Exists(candidate))
                return candidate;

            string? dir = baseDir;
            for (int i = 0; i < 5 && !string.IsNullOrEmpty(dir); i++)
            {
                dir = Directory.GetParent(dir)?.FullName;
                if (string.IsNullOrEmpty(dir))
                    break;

                candidate = Path.Combine(dir, PackageFolder);
                if (Directory.Exists(candidate))
                    return candidate;
            }

            return null;
        }
    }
}
