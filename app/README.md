# MediFlow Android app

See the [project README](../README.md) and [development setup](../docs/development.md) for the implementation status, commands, API configuration, and validation limits.

The app supports Firebase email/password sign-in with server-verified roles. Configure `API_BASE_URL` and the project's public `FIREBASE_API_KEY`; see [authentication setup](../docs/authentication.md). Tokens stay in memory, and sign-out/account changes/expiry clear temporary sensitive bytes.

Debug builds also offer explicitly labeled patient, doctor and administrator interface previews. These are not authenticated sessions and contain no patient records. Release builds cannot enable previews. Document workflow panels remain reserved for later tickets.
