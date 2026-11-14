# Operating SiteGuard QR

## Set up a site

1. Sign in as an organization administrator. In **Administration → Sites**, set the site’s IANA timezone, center coordinates, and approved radius.
2. Under **Employees**, set the employee ID, department, cost code, crew, shift, and assigned sites.
3. Under **Accounts**, create separate foreman, engineer, and timekeeper accounts. A foreman’s optional scope code is the employee’s crew. An engineer’s optional scope code is the project cost code. Select **Employee** and link the roster ID for workers who need the rotating QR.
4. Under **Policy**, confirm QR mode, shift windows, break, missing-out deadline, and overtime rules. Under **Badges**, issue the desired credential. Download static badges from **View QR**. Workers can sign in and open **My badge** to display a rotating code.
5. Under **Terminals**, create the gate’s terminal code. Open **Terminal kiosk** on the installed device and enter its issued credential. Permit the browser’s location request, confirm the gate is within the perimeter, and test an arrival and departure with a fixture badge.

## Run a gate

Start the camera or connect a USB scanner in keyboard-wedge mode with Enter as its suffix. Use **Auto-detect** for routine arrivals and departures. Select **Clock in** or **Clock out** when a shift cannot be identified reliably by proximity. A recorded banner appears after a durable server receipt. **Offline Captured & Sealed** means the event is in the local outbox.

Keep the gate browser profile on the same site origin. Leave the tab open after reconnection or use **Sync now**. Compare the pending and quarantine counts to the **Scan ledger**. Download quarantine receipts before clearing copies that the server has already acknowledged. A mismatch in the device chain requires a supervisor to reconcile the local queue and ledger before any credential rotation.

If a device is retired, disable it in **Administration → Terminals**. Before rotating a functioning terminal’s credential, let queued scans sync and archive any acknowledged quarantine receipts. Re-enroll on the intended device.

## Verify timekeeping

Pick a pay period and site in **Verification**. Open an attendance row to see the raw evidence, review stage, and effective hours.

1. The foreman endorses field evidence, or requests additional evidence.
2. The engineer records the project and overtime disposition, or returns the shift to the foreman.
3. The timekeeper records the final verification or dispute and enters corrected instants with their time offset and a reason when applicable. The existing raw instants are preserved.

Timekeepers can bulk-verify complete, clean shifts. A timekeeper can reopen a final row with a reason. Historical exports remain accessible by revision.

## Hand off the period

1. In **Payroll exports**, review pending shifts, held employee IDs, verified hours, and releasable hours.
2. Generate CSV or XLSX. Download the revision and retain its receipt with the handoff.
3. Use the exact 23-column table for attendance import. Apply the receipt’s employee hold list before releasing anything to downstream payroll. For a site-specific export, the hold list still considers pending shifts elsewhere in the organization.
4. Use **Daily time record** for printable draft output. The draft uses verified gate punches. The receiving agency supplies its approved schedule, missing lunch intervals, undertime, and signatures.

## Optional camera evidence and SSO

Approve the camera policy and retention period before enabling it in the environment and per site. Enter the employee-facing notice and optionally upload the registered badge image. Retained images are visible to scoped timekeepers and auditors from shift details. The workbench records image reads.

For SSO, set up a trusted OpenID Connect client with authorization code flow, `S256` PKCE, and RS256 ID tokens. Register the `/api/v1/auth/oidc/callback` redirect on the canonical HTTPS origin. Create SSO-only accounts with the IdP’s verified email as the username and leave the password blank. SiteGuard binds the first successful verified email match to the issuer and immutable subject within that organization.
