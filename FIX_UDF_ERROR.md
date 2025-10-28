# FIX: Unknown UDF Errors

## Error You're Getting:
```
Unknown user-defined function PDF_ANALYTICS_DB.PDF_PROCESSING.EXTRACT_PDF_TEXT
Unknown user-defined function PDF_ANALYTICS_DB.PDF_PROCESSING.GET_PDF_IMAGE_COUNT
```

## Root Cause:
**The UDFs don't exist in your Snowflake database yet!**

The Streamlit app is trying to call functions that haven't been created.

---

## SOLUTION: Run the Setup Script

### Step 1: Open Snowflake Snowsight
1. Log into your Snowflake account
2. Navigate to **Worksheets** (left sidebar)

### Step 2: Create a New SQL Worksheet
1. Click **+ Worksheet** button
2. Name it "PDF Analytics Setup"

### Step 3: Copy and Execute setup.sql
1. Open the `setup.sql` file from this repository
2. Copy **ALL** the contents (lines 1-179)
3. Paste into the Snowflake worksheet
4. Click **Run All** (or press Ctrl+Enter with everything selected)

### Step 4: Verify the UDFs Were Created
Run this query to confirm:
```sql
USE DATABASE PDF_ANALYTICS_DB;
USE SCHEMA PDF_PROCESSING;

SHOW FUNCTIONS IN SCHEMA PDF_PROCESSING;
```

You should see:
- `EXTRACT_PDF_TEXT`
- `GET_PDF_IMAGE_COUNT`

---

## If UDFs Still Don't Show Up:

### Check 1: Do you have the right permissions?
```sql
-- Run as ACCOUNTADMIN or a role with CREATE FUNCTION privilege
USE ROLE ACCOUNTADMIN;

-- Then re-run the setup.sql
```

### Check 2: Is PyPDF2 available?
Run this test:
```sql
CREATE OR REPLACE FUNCTION TEST_PYPDF2()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.8'
HANDLER = 'test'
PACKAGES = ('pypdf2')
AS
$$
def test():
    import PyPDF2
    return "PyPDF2 is available"
$$;

SELECT TEST_PYPDF2();
```

If this fails, PyPDF2 might not be available in your Snowflake region/account.

### Check 3: Are you using the correct runtime version?
The setup.sql uses `RUNTIME_VERSION = '3.8'`. 

If that doesn't work, try updating setup.sql to use `'3.10'` or `'3.11'`:
```sql
CREATE OR REPLACE FUNCTION EXTRACT_PDF_TEXT(file_path STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'  -- Changed from 3.8
HANDLER = 'extract_text'
PACKAGES = ('pypdf2')
AS
$$
-- ... rest of function
$$;
```

---

## After Creating UDFs:

Once the UDFs are created successfully:

1. Go back to your Streamlit app
2. Try uploading a PDF again
3. Click "Extract Text"
4. The UDFs should now work

---

## Quick Verification Script

Run this after setup.sql to verify everything:

```sql
-- 1. Check database exists
SHOW DATABASES LIKE 'PDF_ANALYTICS_DB';

-- 2. Check schema exists
USE DATABASE PDF_ANALYTICS_DB;
SHOW SCHEMAS LIKE 'PDF_PROCESSING';

-- 3. Check tables exist
USE SCHEMA PDF_PROCESSING;
SHOW TABLES;
-- Should show: PDF_TEXT_DATA, IMAGE_ANALYSIS_RESULTS

-- 4. Check stages exist
SHOW STAGES;
-- Should show: PDF_IMAGES_STAGE, PDF_FILES_STAGE

-- 5. Check UDFs exist
SHOW FUNCTIONS;
-- Should show: EXTRACT_PDF_TEXT, GET_PDF_IMAGE_COUNT

-- 6. Check view exists
SHOW VIEWS;
-- Should show: VW_LATEST_IMAGE_ANALYSIS
```

If all 6 checks pass, your setup is complete and the Streamlit app should work.

---

## Still Having Issues?

If the UDFs still won't create, provide me with:
1. The exact error message from running setup.sql
2. Your Snowflake edition (Enterprise, Business Critical, etc.)
3. Your Snowflake region
4. The output of `SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA();`

