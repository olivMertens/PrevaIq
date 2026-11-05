# PrevaIQ demo assets

Demo files are grouped first by persona and then by scenario:

| Folder | Scenario |
|---|---|
| `property-claims/wine-cellar/` | Flooded wine cellar claim |
| `property-claims/water-damage/` | Building water-damage claim |
| `property-claims/swiss-chocolate-storm/` | Swiss hailstorm claim (Winterthur, CHF, German and English documents, `manifest.json`) |
| `automotive-claims/parking-impact/` | Parking impact with a damaged door |
| `automotive-claims/rear-impact/` | Rear-impact vehicle photo |
| `health-underwriting/` | Life and health underwriting |
| `health-claims/dental/` | Dental claim |
| `mortgage-underwriting/<scenario>/` | Mortgage underwriting variants |
| `communications/` | Reusable customer/insurer email threads |

Scenario-local duplicates are intentional when a demo must be selectable without
assembling files from multiple folders. The in-app demo guide is the source of truth
for the files presented to users.

The Swiss scenario is synthetic: business, people, policy, references and amounts are
fictitious, and the photos are AI-generated (MAI-Image-2.6). Only the municipality and the
storm date are real. `scripts/generate_swiss_storm_claim.py` regenerates the documents and,
with `--photos`, the photos; its `manifest.json` records the prompts, the identity checks
and the three points the analysis should raise. The matching fictitious Swiss policy
conditions are `assets/pdf/prevaiq/prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf`.
