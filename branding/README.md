# Branding

The PDF report and the demo dashboard use ING's colours (orange `#FF6200`, navy `#000066`)
and show the ING logo when it is here.

The logo is a protected trademark and this repository is public, so **the logo file is never
committed** (`.gitignore` keeps everything in this folder out except this README).

1. Get the official logo from ING's brand portal (PNG with a transparent background works best).
2. Save it as `branding/logo.png` on each machine that makes reports (laptop, workbench, server),
   or set `KCT_BRAND_LOGO` in `.env` to where it is.
3. Restart the kernel or the API.

Without the file, the report and dashboard show "ING" as a wordmark in the brand orange.
Check colours and logo use against ING's brand guidelines before a report leaves the bank.
