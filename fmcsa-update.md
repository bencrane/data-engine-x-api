# FMCSA Data Ingest - Status & Next Steps

## Summary

We're building a pipeline to ingest FMCSA (Federal Motor Carrier Safety Administration) data from data.transportation.gov into our Supabase PostgreSQL database for querying and analysis.

## Current State

### What Works
- **Pipeline infrastructure**: The ingest script runs, connects to the database, and logs progress
- **`oos` feed (Out of Service Orders)**: Successfully ingested 1000 rows - this dataset is a proper SODA API dataset
- **Database schema**: Tables exist in `fmcsa` schema (census, daily_changes, authority_history, etc.)
- **Environment**: Doppler-managed env vars for `HQ_DATABASE_URL` and Socrata credentials

### What Doesn't Work
- **5 of 6 feeds return 403 Forbidden**: carrier, auth_hist, boc3, insurance, revocation

## Root Cause

The 403 errors are **NOT an authentication issue**. The problem is that these datasets are **raw file uploads**, not queryable SODA datasets.

When I checked the dataset metadata:
```json
{
  "id": "6qg9-x4f8",
  "name": "Carrier",
  "assetType": "file",          // <-- THIS IS THE PROBLEM
  "blobFilename": "carrier_2026_02_18.txt",
  "blobMimeType": "text/plain"
}
```

The SODA API endpoints (`/resource/{id}.json` or `/api/v3/views/{id}/query.json`) only work on `assetType: "dataset"`. These FMCSA files are uploaded as raw text files.

## Dataset IDs & Types

| Feed | Socrata ID | Asset Type | Status |
|------|------------|------------|--------|
| carrier | 6qg9-x4f8 | file | Needs raw download |
| auth_hist | sn3k-dnx7 | file | Needs raw download |
| boc3 | fb8g-ngam | file | Needs raw download |
| insurance | chgs-tx6x | file | Needs raw download |
| revocation | pivg-szje | file | Needs raw download |
| oos | p2mt-9ige | dataset | Working via SODA API |

## Solution: Download Raw Files

The files ARE accessible - just via a different endpoint:

```
https://data.transportation.gov/api/views/{socrata_id}/files/{blob_id}?download=true
```

### Steps to implement:

1. **Fetch dataset metadata** to get the current `blobId`:
   ```
   GET https://data.transportation.gov/api/views/{socrata_id}.json
   ```
   Response includes: `blobId`, `blobFilename`, `blobFileSize`

2. **Download the raw file**:
   ```
   GET https://data.transportation.gov/api/views/{socrata_id}/files/{blob_id}?download=true
   ```

3. **Parse the CSV** - files are comma-delimited with quoted strings, NO HEADERS

4. **Map columns** - need to define column positions for each feed type

### Sample Data (carrier feed)
```csv
"MC003500","00080356"," ","","A","N","N","N","N","N","N","N","N","Y","N","Y","N","N","00750","Y","N","00750","N","N","Y","","PACIFIC STORAGE COMPANY","3439 BROOKSIDE ROAD #206","","STOCKTON","CA","US","95219","2093206600","2094659533","P O BOX 334","","STOCKTON","CA","US","95201","2093206600",""
```

## Files Modified

- `app/config.py` - Added Socrata credentials to the app settings contract
- `app/ingest/fmcsa_daily.py` - Added `row_limit=1000` for testing, added auth support
- Doppler config - Contains `HQ_DATABASE_URL`, `SOCRATA_KEY_ID`, `SOCRATA_KEY_SECRET`
- `.gitignore` - Excludes `.env`, `.venv/`, `__pycache__/`

## Next Steps

1. **Update `_fetch_all_feed_rows`** to handle file-type assets:
   - Check asset type from metadata
   - If `file`: download blob, parse CSV with column mapping
   - If `dataset`: use existing SODA API approach

2. **Define column mappings** for each CSV feed (no headers in files)

3. **Add date filtering** - The raw files are daily snapshots, so filename includes date (e.g., `carrier_2026_02_18.txt`). We may want to check `blobFilename` to ensure we're getting the right date.

4. **Remove row_limit** once pipeline is verified working end-to-end

## Credentials

Stored in Doppler-managed environment variables:
- `HQ_DATABASE_URL` - Supabase PostgreSQL connection string
- `SOCRATA_KEY_ID` - data.transportation.gov API key ID
- `SOCRATA_KEY_SECRET` - data.transportation.gov API key secret

## Running the Ingest

```bash
source .venv/bin/activate
doppler run -- python scripts/run_fmcsa_ingest.py
# Or for a specific date:
doppler run -- python scripts/run_fmcsa_ingest.py --date 2026-02-18
```
