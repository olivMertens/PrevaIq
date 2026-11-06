# PrevaIQ demo assets

Demo files are grouped first by persona and then by scenario:

| Folder | Scenario |
|---|---|
| `property-claims/wine-cellar/` | Flooded wine cellar claim |
| `property-claims/water-damage/` | Building water-damage claim |
| `property-claims/swiss-chocolate-storm/` | Swiss hailstorm claim (Winterthur, CHF, German and English documents, `manifest.json`) |
| `property-claims/swiss-watch-storm/` | Swiss windstorm claim, large and clean (Schaffhausen watch manufacture, CHF 14.97 million, `manifest.json`) |
| `automotive-claims/parking-impact/` | Parking impact with a damaged door |
| `automotive-claims/rear-impact/` | Rear-impact vehicle photo |
| `health-underwriting/` | Life and health underwriting |
| `health-claims/dental/` | Dental claim |
| `mortgage-underwriting/<scenario>/` | Mortgage underwriting variants |
| `communications/` | Reusable customer/insurer email threads |

Scenario-local duplicates are intentional when a demo must be selectable without
assembling files from multiple folders. The in-app demo guide is the source of truth
for the files presented to users.

## Auto claims and life & health underwriting

- Auto: upload the **two PDFs and one PNG** in `automotive-claims/parking-impact/`.
  The PDFs are email prints, not a signed accident report. Their named attachments
  are not embedded. Vehicle details, policy terms, a signed report and an expert
  estimate must be verified before a final coverage, liability or payout decision.
  The school-insurance request is a separate subject. The photo in `rear-impact/`
  is a different scenario and must not be added as evidence for this collision.
  `scripts/generate_demo_email_threads.py` writes its two auto PDFs to this
  canonical folder by default; `--output-dir` still overrides the destination.
- Underwriting: upload **only** `health-underwriting/souscription-sante-lefevre.pdf`.
  Its three pages contain the request, questionnaire and blood-test results.
  The prescription, identity document, health coverage certificate and bank details
  mentioned in the request are not separate supplied assets.
  `scripts/generate_demo_underwriting.py` regenerates this canonical path.

The demo guide in English, French and German uses these same selections and evidence
limits. Offline asset checks do not certify live extraction, RAG indexing or model output.
The dashboard requires a reachable backend: connection failures show a loading error,
not a fabricated completed case. The API proxy does not substitute local case metadata
for backend errors. Upload the source assets as new cases to test the corrected PDFs.

The Swiss scenario is synthetic: business, people, policy, references and amounts are
fictitious, and the photos are AI-generated (MAI-Image-2.6). Real addresses are used only
as clearly labelled map anchors, not as the depicted premises or occupants:

| Scenario | Real demo map anchor | Verified map position (latitude, longitude) |
|---|---|---|
| Chocolaterie | Steinberggasse 23, 8400 Winterthur, Switzerland | 47.4981698, 8.7292096 |
| Watch manufacture | Mühlentalstrasse 185, 8200 Schaffhausen, Switzerland | 47.7086398, 8.6305155 |

Both addresses were checked in the Swiss official building-address register and resolved
at **building** level through the application's Nominatim geocoder. Sources and coordinates
are recorded in each manifest's `map_anchor`. For the watch anchor, the official register
uses postcode 8200; Nominatim currently labels the same address 8204. Documents retain 8200.
The existing map uses OpenStreetMap geocoding, Esri satellite/OSM plan tiles and external
Google Maps/Street View links, **not Azure Maps**. Street View availability is controlled
by Google and shows the actual location, never the fictional damage or generated interiors.
No actual occupant or building is alleged to have suffered the loss. Existing uploaded
cases retain their old documents: upload the rebuilt set as a new demo case to extract
the new address; editing source assets does not migrate stored cases.

`scripts/generate_swiss_storm_claim.py` regenerates the documents and,
with `--photos`, the photos; its `manifest.json` records the prompts, the identity checks
and the three points the analysis should raise. The matching fictitious Swiss policy
conditions are `assets/pdf/prevaiq/prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf`.

The chocolate upload is **3 PDFs + 6 JPEGs = 9 files**. The two `.eml` files are alternative
attachment bundles, not additional evidence to import with that selection. All six scenes
have per-image system-style construction, metric-scale, power-state and German-text
instructions, prepended to every generation and refinement request. Use `--photos` for all
six, or `--photos PHOTO [PHOTO ...]` for selected scenes; reference edits use a newly generated
parent when available, otherwise its existing JPEG. The before/after shopfront and inside
view share a consistent layout. The awning is retracted before the storm, allowing
wind-driven hail to strike the exposed facade obliquely from above. Laminated safety glass
retains its branching cracks on the interlayer: there are no projectile-like circular
holes or missing centre chunks. Hail is scattered across exposed foreground and street,
with natural variation, not concentrated only beneath the damaged window.
Reported rain ingress is through storm-loosened frame joints, not through solid panes;
the exact leak mechanism still requires technical assessment. Food remains protected in
closed packaging and showcases. The workshop uses real professional chocolate-kitchen
equipment: fitted bowl lids, lidded food containers, moulds, scrapers, scales and a sink.
The wet machine casing does not imply rain poured into an uncovered chocolate vat.
Normal food-protection lids precede the additional external emergency covers at 14:00.
Rain damage is local, heavy furniture remains supported,
and the workshop rooflight belongs to a single-storey rear annex, not a room below upper
floors. There is no tarp in the 11:26 image; emergency covering starts at 14:00.
The cold room is dry: warming alone does not soak cartons or demonstrate spoilage. Its
23.8 °C display shortly after power restoration is a single reading, not a temperature
history or food-safety diagnosis. Photographs show samples, not the claimed inventory.
PDFs, email bundles and guide explain these limits. Technical, inventory and temperature
records are not attached; CHF 1,697,400 remains a provisional demand. The three intentional
coverage/evidence checks (GVZ, refrigerated-goods extension, pre-storm photo) are preserved.

The Swiss watch scenario follows the same rules and uses the same policy conditions: a
fictitious haute horlogerie manufacture in Schaffhausen hit by the real windstorm of
28.08.2026. Unlike the chocolate case, it has no planted fraud or coverage anomaly.
The large claimed loss (CHF 14,968,600, not retail valuation) requires technical and financial
review; building damage is left to the cantonal building insurer. It does not use any real
watch brand, logo or model.
`scripts/generate_swiss_watch_claim.py` regenerates it (`--photos` for the ten photos);
its `manifest.json` records the public sources about the storm, the identity checks and
the expected outcome.

Select **Sinistres Habitation (CH · Watches / Horlogerie / Uhren)** in the in-app demo guide
(English, French and German). Recommended upload: the claim form, the cost estimate,
the two e-mail PDF prints and the ten JPEGs (**14 files**). The `.eml` files are alternative
original e-mail bundles, not additional files to upload with this selection.
They already embed the photos (and the consolidated e-mail also embeds the two
claim PDFs); do not import the same evidence twice. The six first-notice attachments
predate that e-mail; the consolidated estimate includes all ten photos.
The calculated net estimate is **CHF 14,918,600**, after the capped CHF 50,000 deductible,
subject to coverage, damage-scope and valuation review.
Index the Swiss AVB before testing policy-grounded answers.

The PDFs and emails distinguish visible sample damage from the full reported inventory:
three movements, four finished watches, one inspected machining centre and six bagged sample
parts do not establish the totals of 312 calibres, 186 watches or 24 workstations. Exterior
water droplets do not establish internal watch damage. Inventory lists, technical reports,
quotes and business records are referenced but **not included** in the upload set. The
documents describe continuing rain/residual-water ingress after the peak gusts, roof covering
in progress at 14:32, and separately supplied drying equipment the next morning. Building
repairs remain outside the contents/BI demand. Rebuilding documents alone leaves JPEGs intact.

The photo prompts include a targeted realism pass: supported ceiling panels and equipment,
de-energized storm-damaged machines, plausible water diversion and drying setups, coherent
watch holders and movement scale, distinct inventory labels, and consistent low wooded
Schaffhausen surroundings. `--refine PHOTO [PHOTO ...]` reapplies each selected photo's last
correction to its existing image; it rejects unknown, unsupported or missing photos before
connecting to Azure. Re-running the generator rebuilds both e-mail attachment bundles and
the manifest hashes. These automated integrity checks do not replace visual inspection.
When an edit preserves a flawed source layout, `--photos PHOTO [PHOTO ...]` regenerates only
those photos from their full prompts. Paired follow-up photos use the newly generated
reference when selected together, or the existing reference photo otherwise.
The final CNC pair also has minor localized digital retouching of status-indicator lights
to match the isolation timeline. Fresh generation is stochastic: visually check and, if
necessary, repeat that finishing step before rebuilding the bundles and hashes.

The assembly atelier, final-inspection bench and matching next-morning drying view have
been regenerated around interrupted hand assembly, compact individually mounted lamps,
horizontal factory trays and localized damage. Each of these three photos has its own
metric spatial specification and mandatory construction/text instructions, recorded as
`system_instructions` in the manifest. The MAI image routes accept a single `prompt`, not
a chat system role: the generator prepends these instructions to **every generation and
refinement request** for the three scenes, including reference-image edits.

The atelier's opaque soffits stay intact: only skylight glazing is broken, with no mineral
wool emerging from windows or glazing frames. The inspection room has a separate opaque
roof/suspended-ceiling construction. Bench, chair, instrument, tray and watch dimensions
provide explicit relative scales; they are prompt targets, not measured image guarantees.
Readable physical text must be German; the inspection sheet uses `ENDKONTROLLE` with
otherwise empty cells. Do not invent dates, English headings or instrument brands.
Visually inspect construction, scale, support and text after regeneration; automated tests
verify instruction routing and evidence integrity, not the physical truth of rendered pixels.
To regenerate this set together:

```powershell
.\.venv\Scripts\python.exe scripts\generate_swiss_watch_claim.py --photos IMG_20260828_104507.jpg IMG_20260828_110322.jpg IMG_20260829_091744.jpg
```

### Separate luxury wristwatch concept

`assets/design-concepts/rheinkaliber/` contains an **unofficial, AI-generated design study**:
a fictional Rheinkaliber luxury watch worn on a wrist, with Microsoft and GitHub emblems
integrated into its dial. It is not a real product, partnership or endorsement. The logos
belong to their respective owners. **This image is not claim evidence** and is deliberately
kept outside all demo claim folders and e-mail attachments.

`scripts/generate_luxury_watch_concept.py` regenerates it using the same MAI deployment.
Pass `--microsoft-logo` and `--github-logo` with the original logo files; their official
source URLs and hashes, the generation prompt and output hash are recorded in its manifest.
Optionally pass `--reference-watch PATH` with a product-page screenshot: its left watch
column is read without modifying the source and used only for construction, not branding.
The concept keeps its own rose-gold/navy/brown styling with one central three-hand movement,
no small-seconds subdial, an evenly spaced hour/minute track, a crown aligned at 3 o'clock,
and conventional lugs and spring-bar strap attachment. Its manifest records the intended
construction and the reference hash; actual geometry must still be checked in the image.
The generator does not create Azure deployments: a working MAI-Image-2.6 deployment must
be available first (`MAI_IMAGE_ENDPOINT` / `MAI_IMAGE_DEPLOYMENT` override the defaults).
