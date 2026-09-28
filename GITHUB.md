# Publish Vault on GitHub

GitHub hosts the source and downloadable apps through **Releases**. Vault runs on the user's computer; it is not a browser app and does not need GitHub Pages or a server.

## 1. Upload this project

Create an **empty repository** in your GitHub account. Do not generate a README, license, or .gitignore there; the project already contains its documentation and ignore rules. Choose the visibility you want.

With GitHub Desktop, use **File → Add local repository** and choose the `Encrypt_Decrypt` folder itself. If prompted, create a repository in that folder. Review the changed files, commit with a summary such as `Prepare Vault for GitHub`, then choose **Publish repository**. You can let Desktop create the remote instead of first creating an empty repository on the website.

Alternatively, in PowerShell, replace `YOUR_USERNAME` and `YOUR_REPOSITORY` below with your own values:

```powershell
cd "C:\Users\rahul kumar\Downloads\Encrypt_Decrypt"
git init -b main
git rev-parse --show-toplevel
git add .
git status --short
git commit -m "Prepare Vault for GitHub"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

**Check the root before `git add`:** it must end with `Encrypt_Decrypt`, not `Downloads`. A separate Git repository exists in the parent Downloads folder on the original development machine. Initializing this project locally prevents accidentally including unrelated downloads. Do not use `git add` from the parent directory.

Review the staged file list before committing. `.venv`, `.test-deps`, build outputs, logs, `.env` files, `.vault` files, and key files are ignored. Keep any real plaintext documents outside the source repository too.

## 2. Build downloadable apps without local setup

After the first push:

1. Open your repository's **Actions** tab. Enable workflows if GitHub asks.
2. Select **Build desktop apps** → **Run workflow** → choose `main` → **Run workflow**.
3. Wait for the tests and three builds to complete.
4. Open the successful run and download the Windows, macOS, or Linux artifact at the bottom.

Artifacts expire after 14 days and generally require signing into GitHub. Use a published Release for persistent public downloads. Each artifact contains an application archive and a `.sha256` checksum. Extract the outer Actions artifact ZIP, then the application archive inside it.

Tests run on Windows, Linux, and macOS using Python 3.12; Linux also tests the minimum Python 3.10. GUI tests must run in CI rather than silently skip when Tk is unavailable. Linux uses a virtual display. macOS ARM64 and Windows/Linux x64 are the expected hosted-runner builds; check the architecture in the actual archive filename before distributing.

## 3. Create your first release

The app currently declares version **1.0.0** in `vault/__init__.py`. After pushing the code and checking tests:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The **Build desktop apps** workflow tests the code, packages the three native applications, verifies their SHA-256 checksums, and creates a **draft release** with all downloads attached. A tag must match the app version or the build stops. No personal access token is required; the release job uses GitHub's built-in token with repository contents permission.

Open **Releases**, edit the draft named `Vault v1.0.0`, test the downloaded apps on their target systems, edit the release notes, and click **Publish release**. Users then download the appropriate asset:

| Platform | Archive | Launch |
| --- | --- | --- |
| Windows x64 | `Vault-1.0.0-windows-x64.zip` | Extract and double-click `Vault.exe` |
| macOS Apple Silicon | `Vault-1.0.0-macos-arm64.zip` | Extract and open `Vault.app` |
| Linux x64 | `Vault-1.0.0-linux-x64.tar.gz` | Extract, then open/run `Vault` |

Linux builds target Ubuntu 22.04 or newer compatible systems. Builds are unsigned; Windows SmartScreen and macOS Gatekeeper may ask for approval. Signed/notarized distribution needs your own certificates and is not configured here. See [build.md](build.md) for release checks and local packaging.

Do not click GitHub's **Publish release** before the workflow has created its draft: the workflow intentionally refuses to replace assets in an already published release. Reruns can update the draft. A manually dispatched build on a branch only creates workflow artifacts.

For later versions, change `__version__`, commit and push, then push the matching new `vX.Y.Z` tag. Never move an already published tag.

## Repository settings

- Actions must be allowed by the repository/organization. The release job needs `contents: write`; an organization policy can restrict it.
- Consider protecting `main` with the Tests checks required before merge.
- Dependabot is configured for monthly Python dependency and GitHub Actions updates.
- Choose a license before advertising the project as open source. This preparation does not assign a license on your behalf.

References: [GitHub Desktop publishing](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop), [GitHub Actions Python testing](https://docs.github.com/en/actions/tutorials/build-and-test-code/python), [draft releases with GitHub CLI](https://cli.github.com/manual/gh_release_create).
