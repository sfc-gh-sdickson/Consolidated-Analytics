# ⚡ Quick Start Guide
## Deploy in 10 Minutes

This is the fastest path to getting your PDF Processing & Image Analysis app running in Snowflake.

---

## Prerequisites Checklist

Before starting, ensure you have:
- [ ] Snowflake account access
- [ ] Snowsight UI open
- [ ] Role with CREATE DATABASE and CREATE STREAMLIT privileges
- [ ] Cortex AI enabled in your account

---

## Step 1: Run Setup Script (2 minutes)

1. Open Snowsight → **Worksheets**
2. Create new worksheet
3. Copy entire contents of `setup.sql`
4. Click **Run All** (or Ctrl+Enter)
5. Wait for "Setup completed successfully!" message

**Verify:**
```sql
SHOW TABLES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING;
```
Should show: `PDF_TEXT_DATA`, `IMAGE_ANALYSIS_RESULTS`

---

## Step 2: Create Warehouse (1 minute)

```sql
CREATE WAREHOUSE IF NOT EXISTS STREAMLIT_WH
    WAREHOUSE_SIZE = 'MEDIUM'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;
```

---

## Step 3: Create Streamlit App (3 minutes)

1. In Snowsight → **Streamlit** (left sidebar)
2. Click **+ Streamlit App**
3. Fill in form:
   - **App name**: `PDF_Processing_App`
   - **Database**: `PDF_ANALYTICS_DB`
   - **Schema**: `PDF_PROCESSING`
   - **Warehouse**: `STREAMLIT_WH`
4. Click **Create**

---

## Step 4: Add Application Code (2 minutes)

1. Editor opens with default code
2. **Select All** (Ctrl+A) and **Delete**
3. Copy entire contents of `streamlit_app.py`
4. Paste into editor
5. Click **Run** (top right)

---

## Step 5: Install Dependencies (2 minutes)

### Method A: Using Packages Tab
1. Click **Packages** tab in editor
2. Add these packages:
   - `PyMuPDF`
   - `Pillow`
3. Save → App will restart

### Method B: Using Environment File
1. Click **Settings** tab
2. Upload `environment.yml`
3. Save → App will restart

---

## Step 6: Test the App (Immediately)

1. App should now be running
2. Go to **Upload & Process** tab
3. Click "Choose a PDF file"
4. Select `Completed_Product_(Image)_00148568.pdf`
5. Click **Extract Text**
6. Click **Extract Images**
7. Select model from sidebar (try **Pixtral Large**)
8. Click **Run Image Analysis**
9. Go to **Image Analysis** tab to see results

---

## ✅ Success Indicators

You're all set if you can:
- ✅ Upload a PDF file
- ✅ See extracted text in preview
- ✅ See "Successfully uploaded X images" message
- ✅ See analysis progress bar complete
- ✅ View detection metrics (For Sale, Solar, etc.)

---

## 🚨 Troubleshooting

### "Module not found: PyMuPDF"
**Fix:** Go to Packages tab → Add `PyMuPDF` → Save

### "Permission denied"
**Fix:** Run this in SQL worksheet:
```sql
USE ROLE ACCOUNTADMIN;
GRANT USAGE ON DATABASE PDF_ANALYTICS_DB TO ROLE <YOUR_ROLE>;
GRANT ALL ON SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
GRANT ALL ON ALL TABLES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
GRANT READ, WRITE ON ALL STAGES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
```

### "Cortex model not available"
**Fix:** Check if Cortex is enabled:
```sql
SHOW CORTEX FUNCTIONS;
```
If empty, contact your Snowflake account team.

### App is slow
**Fix:** Increase warehouse size:
```sql
ALTER WAREHOUSE STREAMLIT_WH SET WAREHOUSE_SIZE = 'LARGE';
```

---

## 🎯 Next Steps

Now that your app is running:

1. **Explore the UI**
   - Try all three tabs: Upload, Results, Analysis
   - Test with different PDF files
   - Compare different AI models

2. **Query Your Data**
   - Open `example_queries.sql`
   - Run queries to analyze results
   - Create custom queries for your use case

3. **Customize**
   - Edit `streamlit_app.py` to modify UI
   - Adjust analysis prompts for your needs
   - Add new detection categories

4. **Share with Team**
   ```sql
   GRANT USAGE ON STREAMLIT PDF_ANALYTICS_DB.PDF_PROCESSING.PDF_PROCESSING_APP 
   TO ROLE <TEAM_ROLE>;
   ```

---

## 📚 Full Documentation

For detailed information:
- **Setup Guide**: `SETUP_GUIDE.md` - Complete setup with troubleshooting
- **README**: `README.md` - Features, architecture, use cases
- **Example Queries**: `example_queries.sql` - Sample SQL queries

---

## 🆘 Need Help?

1. Check `SETUP_GUIDE.md` → Troubleshooting section
2. Review [Snowflake Docs](https://docs.snowflake.com/)
3. Visit [Snowflake Community](https://community.snowflake.com/)
4. Contact your Snowflake account team

---

**Total Time: ~10 minutes** ⏱️

**You're ready to process PDFs and analyze property images! 🎉**

