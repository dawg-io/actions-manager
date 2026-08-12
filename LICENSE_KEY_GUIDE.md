# License Key Validation for Self-Hosted Installations

This document explains how to use JWT-based license key validation for self-hosted installations of ActionsManager.

## Overview

ActionsManager Self-Hosted is currently a free beta preview. No paid plans are currently available, and features, limits, and license behavior may change before general availability.

Self-hosted installations include JWT-based license-key support for future/commercial tier behavior:
- **Free Tier**: Default tier with limited features (3 projects, 5 repos per project)
- **Professional Tier**: Future/commercial tier behavior; not currently sold during beta
- **Enterprise Tier**: Future/commercial tier behavior; not currently sold during beta

## How It Works

1. **License validation happens at startup**: The application validates the license key when it starts
2. **Result is cached**: The tier is cached for the lifetime of the application process
3. **No network calls**: Validation is purely cryptographic using RS256 JWT signatures
4. **Graceful fallback**: Invalid or expired licenses fall back to the free tier with clear error messages
5. **No secret required**: Customers only need `LICENSE_KEY`. The vendor's public key is embedded in the application.

## Configuration

Add the following to your `.env` file:

```bash
# Self-hosted installation mode
INSTALLATION_MODE=self-hosted

# License key (provided by vendor)
LICENSE_KEY=your_jwt_license_key_here
```

No `LICENSE_SECRET` is required. License signatures are verified using an RSA public key embedded in the application.

## Tier Aliases

The license system supports the following tier names:
- `"free"` - Free tier
- `"professional"` or `"pro"` - Professional tier (both work)
- `"enterprise"` - Enterprise tier

## Testing Your License

### Start the Backend

```bash
cd backend
export LICENSE_KEY="your_license_key"
export INSTALLATION_MODE="self-hosted"
uvicorn main:app --host 0.0.0.0 --port 8000
```

You should see output like:
```
============================================================
🚀 ActionsManager API Starting
📦 Installation Mode: self-hosted
🔑 License Tier: professional
============================================================
```

### Test with Python

```python
import os
os.environ['LICENSE_KEY'] = 'your_license_key'
os.environ['INSTALLATION_MODE'] = 'self-hosted'

import license
tier = license.get_installation_tier()
print(f"Current tier: {tier}")
```

## Error Handling

The system provides clear error messages for common issues:

### Invalid License Format
```
⚠️  License validation failed: Invalid license key format
⚠️  Falling back to free tier
🔑 License Tier: free
```

### Expired License
```
⚠️  License validation failed: License key has expired
⚠️  Falling back to free tier
🔑 License Tier: free
```

### Invalid Signature
```
⚠️  License validation failed: Invalid license key signature
⚠️  Falling back to free tier
🔑 License Tier: free
```

### No License Configured
```
🔑 License Tier: free
```
(No error - just defaults to free tier)

## Cloud Mode vs Self-Hosted Mode

- **Cloud Mode** (`INSTALLATION_MODE=cloud`): Future Cloud/SaaS path; not part of the first public self-hosted beta. License keys are ignored and tiers are intended to be managed through GitHub Marketplace if that offering launches later.
- **Self-Hosted Mode** (`INSTALLATION_MODE=self-hosted`): License keys determine the tier.

## Security Considerations

1. **RS256 asymmetric signing**: Licenses are signed with the vendor's private key and verified with a public key embedded in the application. Customers cannot forge licenses even with full access to the source code.
2. **No secret to protect**: Customers do not hold any signing secret. The private key never leaves the vendor.
3. **Set expiration dates**: Use the `exp` field to limit license duration.
4. **Restart required for changes**: The tier is cached at startup; restart the application after updating `LICENSE_KEY`.

## Troubleshooting

### License validation always fails
- Check that `LICENSE_KEY` environment variable is set correctly
- Ensure there are no extra spaces or newlines in the key
- Ensure the token hasn't expired

### Application shows free tier despite valid license
- Check that `INSTALLATION_MODE` is set to `"self-hosted"`
- Verify there are no typos in the environment variable name
- Check application startup logs for error messages

### Need to test different licenses
- Restart the application after changing `LICENSE_KEY`
- The tier is cached at startup and doesn't change until the application restarts
