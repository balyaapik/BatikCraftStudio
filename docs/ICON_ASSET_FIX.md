# Font Awesome asset loading fix

The application no longer reads `fontawesome_masks.zip` at runtime. Selected
Font Awesome Free 7.3.0 alpha masks are embedded as compressed Base85 text in
`src/batikcraft_studio/ui/fontawesome_assets.py`.

This avoids binary archive corruption in editable Windows source checkouts while
keeping icon rendering fully offline.
