# 📋 Deployment Checklist
## Snowflake PDF Processing & Image Analysis Application

Use this checklist to ensure successful deployment and operation of your application.

---

## Pre-Deployment Checklist

### Account Verification
- [ ] Snowflake account is Enterprise or Business Critical edition
- [ ] Cortex AI is enabled in your region
- [ ] You have access to Snowsight UI
- [ ] You have a role with sufficient privileges

### Privilege Verification
Run these queries to verify:

```sql
-- Check database creation privilege
SHOW GRANTS TO ROLE <YOUR_ROLE>;

-- Check Cortex availability
SHOW CORTEX FUNCTIONS;
```

Expected results:
- CREATE DATABASE privilege on account
- Cortex functions list shows: claude-3-5-sonnet, gpt-4o, pixtral-large

---

## Deployment Steps

### Phase 1: Database Setup
- [ ] Opened Snowsight → Worksheets
- [ ] Created new SQL worksheet
- [ ] Copied and pasted `setup.sql` contents
- [ ] Executed script successfully
- [ ] Verified tables created:
  ```sql
  SHOW TABLES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING;
  ```
  ✅ Should see: `PDF_TEXT_DATA`, `IMAGE_ANALYSIS_RESULTS`

- [ ] Verified stages created:
  ```sql
  SHOW STAGES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING;
  ```
  ✅ Should see: `PDF_IMAGES_STAGE`, `PDF_FILES_STAGE`

### Phase 2: Warehouse Setup
- [ ] Created or identified warehouse for Streamlit
- [ ] Warehouse size is at least SMALL (MEDIUM recommended)
- [ ] Auto-suspend is configured (60 seconds recommended)
- [ ] Auto-resume is enabled
- [ ] Verified warehouse access:
  ```sql
  SHOW GRANTS ON WAREHOUSE <YOUR_WAREHOUSE>;
  ```

### Phase 3: Streamlit App Creation
- [ ] Navigated to Streamlit in Snowsight
- [ ] Clicked "+ Streamlit App"
- [ ] Configured app settings:
  - [ ] App name: `PDF_Processing_App`
  - [ ] Database: `PDF_ANALYTICS_DB`
  - [ ] Schema: `PDF_PROCESSING`
  - [ ] Warehouse: Selected warehouse
- [ ] Clicked Create
- [ ] App editor opened successfully

### Phase 4: Application Code Deployment
- [ ] Deleted default template code
- [ ] Copied `streamlit_app.py` contents
- [ ] Pasted into Streamlit editor
- [ ] Saved the code
- [ ] No syntax errors shown in editor

### Phase 5: Dependencies Installation
Choose ONE method:

**Method A: Packages Tab**
- [ ] Clicked "Packages" tab
- [ ] Added package: `PyMuPDF`
- [ ] Added package: `Pillow`
- [ ] Saved changes
- [ ] App restarted successfully

**Method B: Environment File**
- [ ] Clicked "Settings" tab
- [ ] Uploaded `environment.yml`
- [ ] Saved changes
- [ ] App restarted successfully

### Phase 6: Permissions (if not ACCOUNTADMIN)
- [ ] Ran permission grants:
  ```sql
  USE ROLE ACCOUNTADMIN;
  GRANT USAGE ON DATABASE PDF_ANALYTICS_DB TO ROLE <YOUR_ROLE>;
  GRANT USAGE ON SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
  GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
  GRANT READ, WRITE ON ALL STAGES IN SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <YOUR_ROLE>;
  ```

---

## Testing Checklist

### Test 1: Application Loads
- [ ] Streamlit app shows UI (not error screen)
- [ ] Three tabs visible: "Upload & Process", "View Results", "Image Analysis"
- [ ] Sidebar shows configuration panel
- [ ] Model selection dropdown works

### Test 2: Text Extraction
- [ ] Clicked file uploader
- [ ] Selected `Completed_Product_(Image)_00148568.pdf`
- [ ] File uploaded successfully (✅ message)
- [ ] Clicked "Extract Text" button
- [ ] Saw "Extracting text from PDF..." spinner
- [ ] Got success message with page count
- [ ] Preview shows extracted text

**Verify in database:**
```sql
SELECT * FROM PDF_ANALYTICS_DB.PDF_PROCESSING.PDF_TEXT_DATA;
```
- [ ] Records appear in table

### Test 3: Image Extraction
- [ ] Uploaded same PDF (if not already done)
- [ ] Clicked "Extract Images" button
- [ ] Saw "Extracting images from PDF..." spinner
- [ ] Got success message with image count
- [ ] Success message shows "X images uploaded to stage"

**Verify in stage:**
```sql
LIST @PDF_ANALYTICS_DB.PDF_PROCESSING.PDF_IMAGES_STAGE;
```
- [ ] Image files appear in stage listing

### Test 4: Image Analysis
- [ ] Selected AI model from sidebar (try Pixtral Large)
- [ ] Clicked "Run Image Analysis" button
- [ ] Progress bar appeared
- [ ] Progress bar completed to 100%
- [ ] Got "Analysis complete!" message
- [ ] Navigated to "Image Analysis" tab
- [ ] Saw metrics: For Sale Signs, Solar Panels, Human Presence, Potential Damage
- [ ] Detailed results table shows data

**Verify in database:**
```sql
SELECT * FROM PDF_ANALYTICS_DB.PDF_PROCESSING.IMAGE_ANALYSIS_RESULTS;
```
- [ ] Analysis records appear in table

### Test 5: Results Viewing
- [ ] "View Results" tab shows:
  - [ ] Extracted text records
  - [ ] Extracted images list
  - [ ] Download buttons work
- [ ] "Image Analysis" tab shows:
  - [ ] Summary metrics
  - [ ] Detailed results table
  - [ ] Filter checkboxes work
  - [ ] Download button works

### Test 6: Multiple Models
- [ ] Tested with Claude model
- [ ] Tested with GPT-4o model
- [ ] Tested with Pixtral Large model
- [ ] All models completed successfully
- [ ] Results differ between models (expected)

---

## Performance Checklist

### Application Performance
- [ ] App loads in < 5 seconds
- [ ] Text extraction completes in < 30 seconds for 10-page PDF
- [ ] Image extraction completes in < 30 seconds for 5 images
- [ ] Image analysis completes in < 60 seconds per image

### Database Performance
- [ ] Query results load in < 3 seconds
- [ ] Stage file listings return quickly
- [ ] No timeout errors

**If performance is slow:**
- [ ] Increased warehouse size to MEDIUM or LARGE
- [ ] Verified warehouse is running (not suspended)
- [ ] Checked for warehouse queuing issues

---

## Security Checklist

### Access Control
- [ ] Reviewed who has access to database
- [ ] Reviewed who has access to Streamlit app
- [ ] Sensitive data is properly controlled
- [ ] Stage permissions are appropriate

**Grant access to team members:**
```sql
-- Grant to specific role
GRANT USAGE ON DATABASE PDF_ANALYTICS_DB TO ROLE <TEAM_ROLE>;
GRANT USAGE ON SCHEMA PDF_ANALYTICS_DB.PDF_PROCESSING TO ROLE <TEAM_ROLE>;
GRANT USAGE ON STREAMLIT PDF_ANALYTICS_DB.PDF_PROCESSING.PDF_PROCESSING_APP TO ROLE <TEAM_ROLE>;
```

### Data Protection
- [ ] Reviewed what data is stored in tables
- [ ] Reviewed what images are stored in stages
- [ ] Ensured compliance with data policies
- [ ] Configured appropriate data retention

---

## Production Readiness Checklist

### Documentation
- [ ] Team has access to README.md
- [ ] Team has access to SETUP_GUIDE.md
- [ ] Team has access to example_queries.sql
- [ ] Team knows how to use the application

### Monitoring
- [ ] Know how to check warehouse usage:
  ```sql
  SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
  WHERE WAREHOUSE_NAME = 'STREAMLIT_WH'
  ORDER BY START_TIME DESC;
  ```
- [ ] Know how to check Streamlit app logs
- [ ] Set up alerts for errors (optional)

### Backup & Recovery
- [ ] Understand how to export data:
  ```sql
  COPY INTO @my_stage/backup/
  FROM PDF_TEXT_DATA;
  ```
- [ ] Know how to recreate tables (re-run setup.sql)
- [ ] Know how to restore from backup

### Maintenance
- [ ] Plan for regular cleanup of old data
- [ ] Plan for stage file management
- [ ] Schedule warehouse suspension reviews
- [ ] Update dependencies as needed

---

## Post-Deployment Checklist

### Day 1
- [ ] Monitor first production use
- [ ] Collect user feedback
- [ ] Check for any errors
- [ ] Verify performance is acceptable

### Week 1
- [ ] Review warehouse costs
- [ ] Optimize if needed
- [ ] Address any user issues
- [ ] Document any custom modifications

### Month 1
- [ ] Analyze usage patterns
- [ ] Optimize warehouse size/schedule
- [ ] Clean up old test data
- [ ] Consider adding new features

---

## Troubleshooting Reference

### Common Issues

| Issue | Check | Solution |
|-------|-------|----------|
| "Module not found" | Dependencies installed? | Add package in Packages tab |
| "Permission denied" | Role has grants? | Run permission grants as ACCOUNTADMIN |
| "Table not found" | Setup script ran? | Re-run setup.sql |
| "Warehouse not running" | Warehouse suspended? | Start warehouse or enable auto-resume |
| "Cortex not available" | Region supports it? | Contact Snowflake account team |
| "App is slow" | Warehouse size? | Increase to MEDIUM or LARGE |

### Getting Help

1. **Documentation**: Check SETUP_GUIDE.md → Troubleshooting section
2. **Snowflake Docs**: https://docs.snowflake.com/
3. **Community**: https://community.snowflake.com/
4. **Support**: Contact your Snowflake account team

---

## Success Criteria

✅ **Application is production-ready when:**

- All deployment steps completed
- All tests passing
- Performance is acceptable
- Security controls in place
- Team trained on usage
- Monitoring configured
- Documentation accessible

---

## Sign-Off

- [ ] Deployment completed by: _________________ Date: _________
- [ ] Testing completed by: _________________ Date: _________
- [ ] Security review by: _________________ Date: _________
- [ ] Production approval by: _________________ Date: _________

---

**Congratulations on your successful deployment! 🎉**

For ongoing support, refer to:
- `QUICK_START.md` - Quick reference
- `SETUP_GUIDE.md` - Detailed guide
- `README.md` - Feature overview
- `example_queries.sql` - Query examples

