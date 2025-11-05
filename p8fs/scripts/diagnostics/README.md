# P8FS Diagnostics

End-to-end diagnostic tools for testing P8FS flows before deployment.

## dream_moment_email_flow.py

Comprehensive diagnostic for the dream analysis and moment email workflow.

### What It Does

This script simulates the complete production flow:

1. **Setup Test Tenant** - Creates/updates test tenant with email (amartey@gmail.com)
2. **Create Test Data** - Generates realistic sessions and resources
   - 5 sessions (planning, meetings, reviews, learning, reflection)
   - 10 resources (docs, notes, goals, ideas, feedback)
3. **Run Dream Analysis** - Analyzes sessions/resources using LLM (direct mode, no batch)
   - Collects user data from last 24 hours
   - Runs LLM analysis to extract goals, dreams, fears, tasks
   - Shows analysis results and confidence scores
4. **Create Moments** - Generates moments from dream analysis
   - Creates insight moments from executive summary
   - Creates goal moments from identified goals
5. **Preview Moment Email** - Generates HTML email preview
   - Uses MomentEmailBuilder for beautiful formatting
   - Saves HTML to `/tmp/moment_email_preview_<tenant-id>.html`
   - Shows email details (subject, recipient, moment count)
6. **Test Scheduled Task** - Runs the scheduled email task
   - Preview mode (default): Shows what would be sent
   - Send mode (`--send-email`): Actually sends email
7. **Show Statistics** - Displays record counts and metrics
   - Sessions, resources, moments counts
   - Creation statistics
   - Error tracking

### Usage

```bash
# Local PostgreSQL (default)
P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/diagnostics/dream_moment_email_flow.py

# Production TiDB (on cluster)
P8FS_STORAGE_PROVIDER=tidb uv run python scripts/diagnostics/dream_moment_email_flow.py

# Skip data creation if it already exists
uv run python scripts/diagnostics/dream_moment_email_flow.py --skip-data-creation

# Actually send email (default is preview only)
uv run python scripts/diagnostics/dream_moment_email_flow.py --send-email

# Custom tenant and email
uv run python scripts/diagnostics/dream_moment_email_flow.py \
  --tenant-id my-tenant \
  --email user@example.com
```

### Testing on Production Cluster

To test with the production TiDB database on the cluster:

```bash
# On the cluster (in a pod with database access)
kubectl exec -it -n p8fs deployment/p8fs-scheduler -- /bin/bash

# Inside the pod
python scripts/diagnostics/dream_moment_email_flow.py --tenant-id tenant-test

# Check the email preview
cat /tmp/moment_email_preview_tenant-test.html
```

### What to Expect

**Successful Run Output:**
```
╭──────────────────────────────────────╮
│ Dream & Moment Email Flow Diagnostic │
│                                      │
│ Provider: postgresql                 │
│ Tenant: tenant-test                  │
│ Email: amartey@gmail.com             │
│ Send Email: False                    │
╰──────────────────────────────────────╯

✓ Tenant tenant-test already exists
✓ Created 5 sessions
✓ Created 10 resources
✓ Found 5 sessions, 10 resources for analysis
✓ Dream analysis completed
✓ Created 4 moments from analysis
✓ Email preview saved to /tmp/moment_email_preview_tenant-test.html
✓ Scheduled task tested (preview mode)

    Diagnostic Run Statistics
╭───────────────────────┬───────╮
│ Metric                │ Count │
├───────────────────────┼───────┤
│ Sessions Created      │     5 │
│ Resources Created     │    10 │
│ Dreams Analyzed       │     1 │
│ Moments Created       │     4 │
│ Emails Sent/Previewed │     1 │
│ Errors                │     0 │
╰───────────────────────┴───────╯
```

**Record Counts After Run:**
```
Records for tenant-test
╭───────────┬───────╮
│ Type      │ Count │
├───────────┼───────┤
│ Sessions  │    5  │
│ Resources │   10  │
│ Moments   │    4  │
╰───────────┴───────╯
```

### Viewing the Email Preview

The script saves an HTML preview of the moment email. To view it:

```bash
# Open in browser (macOS)
open /tmp/moment_email_preview_tenant-test.html

# Open in browser (Linux with xdg-open)
xdg-open /tmp/moment_email_preview_tenant-test.html

# Or copy the content to view elsewhere
cat /tmp/moment_email_preview_tenant-test.html
```

### Email Format

The moment email uses the `MomentEmailBuilder` which creates:

- **Subject:** `EEPIS Moments: {moment_name}`
- **From:** `saoirse@dreamingbridge.io` (configured in email service)
- **To:** Tenant's email from database (or fallback for test tenants)
- **Content:**
  - Moment title and type
  - Full moment content
  - Metadata (location, mood, timestamps)
  - Beautiful HTML formatting with styling

### Verifying Cluster Health

This diagnostic is perfect for cluster health checks:

1. **Regular Runs:** Schedule this diagnostic to run periodically
2. **Email Verification:** Use `--send-email` to verify email delivery
3. **Database Health:** Check that records are being created correctly
4. **LLM Integration:** Verify OpenAI API connectivity and analysis quality
5. **End-to-End Flow:** Confirms entire pipeline from data → analysis → email

### Common Issues

**Issue:** "No sessions/resources found"
- **Solution:** Run without `--skip-data-creation` to generate test data

**Issue:** "Dream analysis failed"
- **Solution:** Check `OPENAI_API_KEY` environment variable is set
- **Solution:** Verify network connectivity to OpenAI API

**Issue:** "Email sending failed"
- **Solution:** Check email configuration in `p8fs_cluster.config.settings`
- **Solution:** Verify SMTP credentials and server access

**Issue:** "Database connection failed"
- **Solution:** Check `P8FS_STORAGE_PROVIDER` matches available database
- **Solution:** Verify database connection string in centralized config

### Next Steps After Successful Run

1. **Review Email Preview** - Check HTML formatting and content quality
2. **Test with Real Data** - Run with `--skip-data-creation` on production tenant
3. **Deploy Scheduler** - Deploy moment email scheduled tasks to cluster
4. **Monitor Emails** - Verify regular emails arrive for test tenant (amartey@gmail.com)
5. **Production Rollout** - Enable for all active tenants

### Integration with Scheduler

This diagnostic tests the same code path that the scheduled tasks use:

- `send_tenant_moment_emails` - Every 3 hours
- `send_daily_moment_summary` - Daily at 9 AM UTC

After successful diagnostic runs, deploy the scheduler to enable automated moment emails for all tenants.
