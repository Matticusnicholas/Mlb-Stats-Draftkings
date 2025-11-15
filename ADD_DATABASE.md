# How to Add Your Database to the Repository

Your database file (`mlb_stats.db`) is now configured to be tracked by Git!

## Quick Steps:

### 1. Copy your database file to the data folder

```bash
# Make sure you're in the project root directory
# Copy your database file to data/mlb_stats.db
copy "C:\path\to\your\mlb_stats.db" "data\mlb_stats.db"
```

### 2. Check that Git can see it

```bash
git status
```

You should see `data/mlb_stats.db` listed as a new file.

### 3. Add and commit it

```bash
git add data/mlb_stats.db
git commit -m "Add MLB stats database with 2025 data"
git push
```

## Why This Works Now:

The `.gitignore` file has been updated to **allow** `data/mlb_stats.db` specifically, even though it ignores other `.db` files. This is done with this exception:

```gitignore
# Database
*.db                    # Ignore all .db files
!data/mlb_stats.db      # BUT allow this specific file (! means exception)
```

## Notes:

- **File Size**: If your database is very large (>100MB), you may need to use Git LFS (Large File Storage)
- **Updates**: Whenever you fetch new MLB data, commit and push the updated database
- **Sharing**: Once pushed, anyone who clones the repo will get your database automatically!

## Checking File Size:

Before adding, check how big your database is:

```bash
# Windows
dir data\mlb_stats.db

# Linux/Mac
ls -lh data/mlb_stats.db
```

If it's over 100MB, you'll need Git LFS:

```bash
# Install Git LFS (one time only)
git lfs install

# Track the database with LFS
git lfs track "data/mlb_stats.db"

# Then add and commit normally
git add .gitattributes data/mlb_stats.db
git commit -m "Add MLB stats database with Git LFS"
git push
```

## Alternative: Keep Database Separate

If you prefer NOT to track the database in Git (keeps repo lighter):

1. Don't add it to Git
2. Keep it backed up separately (Dropbox, Google Drive, etc.)
3. When cloning the repo on a new machine, just copy the database to `data/`
4. The batch files will check for it before running

The choice is yours! Both approaches work.
