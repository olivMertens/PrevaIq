const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { createTranslator } = require('use-intl/core');
const { load: loadTs, srcDir } = require('./loadTs');

const caseDir = path.join(srcDir, 'components', 'case');
const libDir = path.join(srcDir, 'lib');
const propertyDir = path.join(srcDir, 'components', 'claims', 'property');
const load = (name, dir = caseDir) => loadTs(name, dir);
const { swissGermanMessages } = loadTs('locales.ts', path.join(srcDir, 'i18n'));
const locales = ['en', 'fr', 'de', 'de-CH'];
const messagesFor = (locale) => {
  const messages = JSON.parse(fs.readFileSync(
    path.join(srcDir, '..', 'messages', `${locale === 'de-CH' ? 'de' : locale}.json`), 'utf8'
  ));
  return locale === 'de-CH' ? swissGermanMessages(messages) : messages;
};

const signals = load('caseSignals.ts');
const updates = load('caseUpdates.ts');
const health = load('pipelineHealth.ts');
const recommendation = load('recommendation.ts');
const currency = load('currency.ts', libDir);
const display = load('applicationDisplay.ts', libDir);
const timelineDates = load('timelineDates.ts', libDir);
const analysisMarkdown = load('analysisMarkdown.ts', propertyDir);
const coverageView = load('coverageView.ts', propertyDir);
const propertySignals = load('buildPropertySignals.ts', propertyDir);
const {assessAuroraClaimWindow} = loadTs('auroraClaimTime.ts', libDir);

test('claim weather comparison distinguishes an event hour from an overlapping calendar day', () => {
  const series = [
    {valid_at: '2026-08-28T07:00:00Z'}, {valid_at: '2026-08-28T12:00:00Z'},
  ];
  assert.equal(assessAuroraClaimWindow(series), 'missing_date');
  assert.equal(assessAuroraClaimWindow(series, '31/02/2026'), 'invalid_date');
  assert.equal(assessAuroraClaimWindow(series, '28/08/2026'), 'same_day');
  assert.equal(assessAuroraClaimWindow(series, '2026-08-28T09:00:00+02:00'), 'within_window');
  assert.equal(assessAuroraClaimWindow(series, '2026-08-28T12:00:00Z'), 'within_window');
  assert.equal(assessAuroraClaimWindow(series, '2026-08-28T12:00:01Z'), 'outside_window');
  assert.equal(assessAuroraClaimWindow(series, '2030-08-28'), 'outside_window');
  assert.equal(assessAuroraClaimWindow([], '2026-08-28'), 'unavailable');
  assert.equal(assessAuroraClaimWindow([...series].reverse(), '2026-08-28'), 'unavailable');
  assert.equal(assessAuroraClaimWindow([{valid_at: 'invalid'}], '2026-08-28'), 'unavailable');
});

test('case categories follow the UI locale before compacting, without changing holder names', () => {
  const { localizeApplicationTitle, compactApplicationTitle, localizeClaimSubject } = display;
  const cases = [
    ['Schoggimanufaktur Eulachblick GmbH — Grêle / tempête (dommage élémentaire)',
      { en: 'Hail / Storm (Natural hazards)', fr: 'Grêle / Tempête (Dommages élémentaires)', de: 'Hagel / Sturm (Elementarschaden)' }],
    ['Olivier MERTENS LAFFITE — Dégâts des eaux - infiltration suite à tempête',
      { en: 'Water damage - Water ingress following a storm', fr: 'Dégâts des eaux - Infiltration suite à tempête', de: 'Wasserschaden - Wassereintritt nach Sturm' }],
    ['MARTIN Claire — Dommages structure',
      { en: 'Structural damage', fr: 'Dommages structurels', de: 'Strukturschäden' }],
    ['LECOMTE Sandrine — Inondation',
      { en: 'Flooding', fr: 'Inondation', de: 'Überschwemmung' }],
  ];
  for (const locale of locales) {
    const subjects = messagesFor(locale).claimSubjects;
    const translate = (key) => {
      assert.equal(typeof subjects[key], 'string', `missing ${locale}.${key}`);
      return subjects[key];
    };
    for (const [source, expected] of cases) {
      const localized = localizeApplicationTitle(source, translate);
      assert.equal(localized, `${source.split(' — ')[0]} — ${expected[locale] || expected.de}`);
      assert.equal(
        compactApplicationTitle(localized).holder,
        compactApplicationTitle(source).holder
      );
      // Switching locale uses the original data, and already localized labels stay stable.
      assert.equal(localizeApplicationTitle(localized, translate), localized);
    }
    assert.equal(localizeApplicationTitle('Tempête SARL', translate), 'Tempête SARL');
    assert.equal(localizeApplicationTitle('Flood — POL-FR-001', translate), 'Flood — POL-FR-001');
    assert.equal(localizeClaimSubject('Water damage caused by the neighbour upstairs', translate),
      'Water damage caused by the neighbour upstairs');
    assert.equal(localizeClaimSubject('Inondation exceptionnelle non classée', translate),
      'Inondation exceptionnelle non classée');
    assert.equal(localizeClaimSubject('', translate), '');
  }
});

test('known English and German claim labels also translate into French', () => {
  const fr = JSON.parse(fs.readFileSync(path.join(srcDir, '..', 'messages', 'fr.json'), 'utf8')).claimSubjects;
  const translate = (key) => fr[key];
  assert.equal(display.localizeClaimSubject('Hail / Storm', translate), 'Grêle / Tempête');
  assert.equal(display.localizeClaimSubject('Hagel / Sturm (Elementarschaden)', translate),
    'Grêle / Tempête (Dommages élémentaires)');
  assert.equal(display.localizeClaimSubject('Structural damage', translate), 'Dommages structurels');
  assert.equal(display.localizeClaimSubject('ÉLEVÉ', translate), 'Élevé');
});

// Coverage and settlement analyses as the LLM wrote them (trimmed from production cases).
const citation = (criteria, article, why) => ({
  policy_id: criteria.slice(0, -2),
  criteria_id: criteria,
  policy_name: `Gebäude bei der kantonalen Gebäudeversicherung (${article})`,
  matched_condition: 'Gebäudeschaden in einem Kanton mit kantonaler Gebäudeversicherung',
  applied_action: 'Gebäudepositionen ausschliessen',
  rationale: why,
});
const swissCoverage = {
  overall_status: 'partially_covered',
  event_assessment: { cause: 'Hagel / Sturm (Elementarschaden)', covered_event: true },
  coverage_decisions: [
    { risk: 'DDE', covered: true, coverage_status: 'covered_as_consequential_water_damage', explanation: 'Water came in through broken skylights.', policy_citations: [] },
    { risk: 'tempête', covered: true, coverage_status: 'covered', explanation: 'Hail and storm are insured perils.' },
    { risk: 'incendie', covered: false, coverage_status: 'not_triggered', explanation: 'No fire is described.' },
  ],
  exclusions_applicable: [
    { item: 'Building items', status: 'excluded_from_this_policy', explanation: 'Insured by the GVZ.', policy_citations: [citation('CH-AVB-GEB-002-A', 'AVB Ziff. B1.3', 'Building items are claimed.')] },
  ],
  franchise: { applies: true, deductible_rule: "10% of the indemnity, minimum CHF 2'500, maximum CHF 50'000" },
  irsi: { applies: false, reason: 'French convention only.' },
  cat_nat: { applies: false, reason: 'No Cat-Nat regime in Switzerland.' },
  applicable_articles: ['AVB Ziff. B2.1', 'AVB Ziff. B1.3'],
  claim_level_summary: { status: 'partial_coverage', covered_core_peril: 'Hail and storm', main_uncovered_items: ['building items under GVZ'] },
};
const swissSettlement = {
  currency: 'CHF',
  estimated_repairs: 798500,
  deductible_applicable: 50000,
  recommended_indemnity: 748500,
  complementary_expertise_required: true,
  third_party_recourse_possible: true,
  third_party_recourse_basis: ['GVZ', 'third_party_liability_if_identified'],
  conditions: [
    { item: 'Building items', amount: 184000, coverage_status: 'excluded_from_this_settlement', reason: 'GVZ.' },
    { item: 'Stock', amount: 312500, coverage_status: 'covered', reason: 'Elementar damage.' },
    { item: 'Business interruption', amount: 398000, coverage_status: 'provisional_review_needed', reason: 'To separate.' },
    { item: 'Production equipment', amount: 486000, coverage_status: 'covered', reason: 'Elementar damage.' },
  ],
  policy_citations: [citation('CH-AVB-GEB-002-A', 'AVB Ziff. B1.3', 'Duplicate of the coverage citation.')],
};

test('coverage view reads a Swiss analysis: verdict, items, guarantees, rules and articles', () => {
  const { buildCoverageView, sortByTone, amountBreakdown } = coverageView;
  const view = buildCoverageView(swissCoverage, swissSettlement);

  assert.equal(view.tone, 'partial');
  assert.equal(view.coveredHighlight, 'Hail and storm');
  assert.deepEqual(view.notCoveredHighlights, ['building items under GVZ']);
  assert.deepEqual(view.event, { cause: 'Hagel / Sturm (Elementarschaden)', covered: true });
  assert.deepEqual(view.amounts, { eligible: 798500, deductible: 50000, recommended: 748500 });
  assert.deepEqual(view.guarantees.map((item) => [item.peril, item.tone]), [
    ['water', 'covered'], ['storm', 'covered'], ['fire', 'notConcerned'],
  ]);
  // The exclusion matches an excluded claim item: shown once, on the item, with its article.
  assert.deepEqual(view.exclusions, []);
  assert.deepEqual(sortByTone(view.lines).map((item) => [item.name, item.tone, item.references]), [
    ['Stock', 'covered', []],
    ['Production equipment', 'covered', []],
    ['Business interruption', 'review', []],
    ['Building items', 'excluded', ['AVB Ziff. B1.3']],
  ]);
  assert.deepEqual(amountBreakdown(view, 1380500), [
    { kind: 'covered', amount: 798500, percent: 58 },
    { kind: 'review', amount: 398000, percent: 29 },
    { kind: 'excluded', amount: 184000, percent: 13 },
  ]);
  assert.deepEqual(view.rules.deductible, {
    applies: true, amount: undefined, detail: "10% of the indemnity, minimum CHF 2'500, maximum CHF 50'000", reason: undefined,
  });
  assert.equal(view.rules.catNat.applies, false);
  assert.equal(view.rules.irsi.reason, 'French convention only.');
  assert.equal(view.rules.expertise.applies, true);
  assert.deepEqual(view.rules.recourse, { applies: true, against: ['GVZ', 'third_party_liability_if_identified'] });
  // Codes are shown humanized, and only in an English UI (the backend does not translate them).
  assert.equal(coverageView.isCode('third_party_liability_if_identified'), true);
  assert.equal(coverageView.isCode('GVZ'), false);
  assert.equal(coverageView.humanizeCode('third_party_liability_if_identified'), 'Third party liability if identified');
  assert.equal(view.deductibleMismatch, undefined);
  // One card per policy criterion; the article moves out of the quoted policy name.
  assert.deepEqual(view.citations.map((item) => [item.reference, item.id, item.name, item.why]), [
    ['AVB Ziff. B1.3', 'CH-AVB-GEB-002-A', 'Gebäude bei der kantonalen Gebäudeversicherung', 'Building items are claimed.'],
  ]);
  assert.deepEqual(view.articles.map((item) => item.reference), ['AVB Ziff. B2.1', 'AVB Ziff. B1.3']);
});

test('coverage view reads French analyses written as maps and nested objects', () => {
  const { buildCoverageView, amountBreakdown } = coverageView;
  const mapForm = buildCoverageView(
    {
      statut_couverture: 'couvert_partiellement_sous_reserve',
      garantie: {
        dde: { couvert: true, motif: 'Infiltration after the storm.', observations: ['Water came through a vent.'] },
        rc: { couvert: false, motif: 'No third party.' },
      },
      exclusions_applicables: [{ exclusion: 'Lack of maintenance', impact: 'Point of attention', motif: 'Blocked gutter.' }],
      franchise: { franchise_applicable: 250, devise: 'EUR', motif: 'DDE deductible.' },
      articles_applicables: [{ article: 'Garantie Dégâts des eaux', effet: 'Covers infiltrations.' }],
      synthese: 'Covered under water damage, subject to an expert appraisal.',
    },
    {
      montant_estime_reparations: 10825,
      franchise_applicable: 380,
      montant_indemnisation_recommandee: 10445,
      expertise_complementaire_necessaire: { requise: true, motif: 'Above €5,000.', delai_suggere: 'Within 5 business days' },
      recours_possible: { irsi: { applicable: false, motif: 'Detached house.' }, tiers: { applicable: false, motif: 'No liable third party.' } },
      conditions: ['Subject to supporting documents.'],
      commentaire: 'Settle €10,445 after the €380 deductible.',
    },
  );
  assert.equal(mapForm.tone, 'partial');
  assert.equal(mapForm.summary, 'Covered under water damage, subject to an expert appraisal.');
  assert.deepEqual(mapForm.guarantees.map((item) => [item.name, item.peril, item.tone, item.notes]), [
    ['dde', 'water', 'covered', ['Water came through a vent.']],
    ['rc', 'liability', 'notConcerned', []],
  ]);
  assert.deepEqual(mapForm.exclusions.map((item) => [item.name, item.tone]), [['Lack of maintenance', 'review']]);
  assert.deepEqual(mapForm.amounts, { eligible: 10825, deductible: 380, recommended: 10445 });
  assert.deepEqual(mapForm.deductibleMismatch, { coverage: 250, settlement: 380 });
  assert.deepEqual(mapForm.rules.expertise, { applies: true, detail: 'Within 5 business days', reason: 'Above €5,000.' });
  assert.deepEqual(mapForm.rules.recourse, { applies: false, reason: 'No liable third party.', against: [] });
  assert.deepEqual(mapForm.conditions, ['Subject to supporting documents.']);
  assert.equal(mapForm.settlementNote, 'Settle €10,445 after the €380 deductible.');
  assert.deepEqual(mapForm.articles, [{ reference: 'Garantie Dégâts des eaux', status: undefined, tone: 'unknown', effect: 'Covers infiltrations.' }]);
  assert.deepEqual(amountBreakdown(mapForm, 10825), []);

  const nested = buildCoverageView(
    {
      statut_couverture: {
        decision: 'couvert_partiellement',
        resume: 'Covered as storm water damage.',
        garanties_concernees: [
          { garantie: 'Tempête', couverture: 'oui', motif: 'Storm Gérard.' },
          { garantie: 'Theft / vandalism', couverture: 'non_demontree', motif: 'Not confirmed.' },
        ],
      },
      exclusions_applicables: { decision: 'aucune_exclusion_certaine_identifiee', resume: 'No certain exclusion.', points_de_vigilance: ['Old seepage is not covered.'] },
      articles_applicables: [{ article: 'Régime Cat-Nat', conclusion: 'Not retained as it stands', motif: 'No order.' }],
    },
    {
      montants: { montant_estime_reparations: 2728, franchise_applicable: 380, montant_indemnisation_recommande: 2348 },
      conditions: {
        base_de_calcul: ["Plumber's invoice: €1,556.50"],
        franchise: 'Storm deductible applied at €380.',
        expertise_complementaire: { necessaire: false, motif: 'Below €5,000.' },
        recours_possible: { irsi: false, responsabilite_tiers: false, commentaire: 'No liable third party.' },
      },
      decision_recommandee: { statut: 'accord_partiel', montant_recommande: 2348, commentaire: 'Settle the justified repairs.' },
    },
  );
  assert.equal(nested.tone, 'partial');
  assert.equal(nested.summary, 'Covered as storm water damage.');
  assert.deepEqual(nested.guarantees.map((item) => [item.peril, item.tone]), [['storm', 'covered'], ['theft', 'review']]);
  assert.equal(nested.exclusionsSummary, 'No certain exclusion.');
  assert.deepEqual(nested.attention, ['Old seepage is not covered.']);
  assert.deepEqual(nested.amounts, { eligible: 2728, deductible: 380, recommended: 2348 });
  assert.deepEqual(nested.basis, ["Plumber's invoice: €1,556.50"]);
  assert.deepEqual(nested.conditions, ['Storm deductible applied at €380.']);
  assert.deepEqual(nested.rules.expertise, { applies: false, detail: undefined, reason: 'Below €5,000.' });
  assert.equal(nested.rules.recourse.applies, false);
  assert.equal(nested.settlementNote, 'Settle the justified repairs.');
  assert.deepEqual(nested.articles.map((item) => [item.status, item.tone]), [['Not retained as it stands', 'notConcerned']]);
  // Without item amounts, the claimed amount splits into retained and not retained.
  assert.deepEqual(amountBreakdown(nested, 6560), [
    { kind: 'covered', amount: 2728, percent: 42 },
    { kind: 'notRetained', amount: 3832, percent: 58 },
  ]);
});

test('coverage statuses and perils are read in English, French and German', () => {
  const { statusTone, perilKey, coverageOutputs, buildCoverageView } = coverageView;
  const cases = [
    [true, 'covered'], [false, 'excluded'], ['oui', 'covered'], ['non', 'excluded'], ['Gedeckt', 'covered'],
    ['partially_covered', 'partial'], ['couvert_partiellement_sous_reserve', 'partial'],
    ['excluded_without_additional_coverage', 'excluded'], ['provisional_review_needed', 'review'],
    ['Applicable subject to confirmation', 'review'], ['confirmed', 'covered'], ['not_triggered', 'notConcerned'],
    ['Not applicable', 'notConcerned'], ['', 'unknown'], [undefined, 'unknown'],
  ];
  for (const [status, tone] of cases) assert.equal(statusTone(status), tone, String(status));
  assert.equal(perilKey('Dégâts des eaux'), 'water');
  assert.equal(perilKey('Third-party liability'), 'liability');
  assert.equal(perilKey('Hagel'), 'hail');
  assert.equal(perilKey('Water damage caused by the neighbour upstairs'), undefined);

  const outputs = coverageOutputs({
    liability_assessment: { coverage_verification: { parsed: { overall_status: 'covered' } } },
    payout_recommendation: { settlement_analysis: { parsed: { recommended_amount: '€1,900.00' } } },
    damage_assessment: { visual_damage_analysis: { parsed: { _error: 'Failed to parse JSON response.' } } },
  });
  assert.deepEqual(outputs, { coverage: { overall_status: 'covered' }, settlement: { recommended_amount: '€1,900.00' } });
  assert.equal(buildCoverageView(outputs.coverage, outputs.settlement).amounts.recommended, 1900);
  assert.equal(buildCoverageView(undefined, undefined).hasContent, false);
  // A sentence is not an amount.
  assert.equal(buildCoverageView(undefined, { franchise: 'Storm deductible applied at €380 per the policy terms.' }).amounts.deductible, undefined);

  // Booleans of the analyses read as yes / no in every language.
  for (const [locale, answers] of Object.entries({ en: ['Yes', 'No'], fr: ['Oui', 'Non'], de: ['Ja', 'Nein'] })) {
    const fields = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'messages', `${locale}.json`), 'utf8')).claims.parsedFields;
    assert.deepEqual([fields.yes, fields.no], answers, locale);
  }
});

test('structured analyses render as readable Markdown, not run-together lines', () => {
  const { analysisFieldsMarkdown, parseAiSummary, humanizeFieldKey } = analysisMarkdown;
  const markdown = analysisFieldsMarkdown({
    coverage_status: 'covered_with_deductible',
    requires_human_review: false,
    total_amount: 14968600,
    cat_nat: true,
    damages: [
      { item: 'Flat roof membrane', cost: 182000 },
      { item: 'Clean room', cost: 960000 },
    ],
    _internal: 'hidden',
  }, { money: (value) => `CHF ${value}`, yes: 'Yes', no: 'No' });

  assert.equal(markdown, [
    '- **Coverage status:** Covered with deductible',
    '- **Requires human review:** No',
    '- **Total amount:** CHF 14968600',
    '- **Cat-Nat:** Yes',
    '',
    '#### Damages',
    '- **Flat roof membrane**',
    '  - **Cost:** CHF 182000',
    '- **Clean room**',
    '  - **Cost:** CHF 960000',
  ].join('\n'));
  assert.equal(humanizeFieldKey('irsi_convention'), 'IRSI convention');

  const tabs = parseAiSummary('Intro\n\n#### Damages\n- roof\n\n---\n\n#### Fraud indicators\n- none');
  assert.equal(tabs.overview, 'Intro');
  assert.equal(tabs.damages, '#### Damages\n- roof');
  assert.equal(tabs.risk, '#### Fraud indicators\n- none');
});

test('timeline previews are plain text cut at a word boundary', () => {
  const { markdownPreview } = analysisMarkdown;
  assert.equal(markdownPreview('## Summary\n**Storm** damage confirmed by [MeteoSwiss](https://x.ch).'), 'Summary');
  assert.equal(markdownPreview('- **Storm** damage confirmed by [MeteoSwiss](https://x.ch).'), 'Storm damage confirmed by MeteoSwiss.');
  const preview = markdownPreview('The hail storm of 28 August damaged the flat roof and the clean room of the workshop', 40);
  assert.ok(preview.length <= 40, preview);
  assert.ok(preview.endsWith('…'), preview);
  assert.ok(!/\s…$/.test(preview), preview);
  assert.equal(markdownPreview('file_name_v2 stays intact'), 'file_name_v2 stays intact');
});

test('timeline dates accept ISO and European formats', () => {
  const { parseTimelineDate, formatTimelineDate } = timelineDates;
  const iso = parseTimelineDate('2026-08-28T10:05:00Z');
  for (const text of ['28/08/2026', '28.08.2026', 'le 28-08-2026 vers 10h']) {
    const date = parseTimelineDate(text);
    assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate()], [2026, 7, 28], text);
  }
  assert.deepEqual([iso.getFullYear(), iso.getMonth(), iso.getDate()], [2026, 7, 28]);
  assert.equal(parseTimelineDate('31/13/2026').getFullYear(), 2026);
  assert.equal(parseTimelineDate('no date'), null);
  assert.deepEqual(formatTimelineDate(new Date(2026, 7, 28), 'en'), { date: 'Aug 28', year: '2026' });
  assert.deepEqual(formatTimelineDate(null, 'en'), { date: '—', year: '' });
});

test('long case titles are shown compact, short ones unchanged', () => {
  const { compactApplicationTitle } = display;
  const compact = (title) => compactApplicationTitle(title).text;

  assert.equal(
    compact('Olivier MERTENS LAFFITE — Dégâts des eaux - infiltration suite à tempête'),
    'O. MERTENS LAFFITE · Dégâts des eaux',
  );
  assert.equal(
    compact('MERTENS LAFFITE Olivier — Dégâts des eaux - infiltration suite à tempête'),
    'MERTENS LAFFITE O. · Dégâts des eaux',
  );
  assert.equal(
    compact('Schoggimanufaktur Eulachblick GmbH — Grêle / tempête (dommage élémentaire)'),
    'Schoggimanufaktur Eulachblick · Grêle / tempête',
  );
  assert.equal(compact('RENARD Christophe (flotte SARL Renard Transport)'), 'RENARD Christophe');
  assert.equal(
    compact('Mertens Olivier — Collision / frottement latéral avec bris de glace'),
    'Mertens Olivier · Collision / frottement…',
  );
  assert.equal(compact('Jean-Pierre Marie DUPONT-MOREAU — Vol'), 'J.-P. M. DUPONT-MOREAU · Vol');
  // Not a "given names + SURNAME" shape: left as written.
  assert.equal(compact('Boulangerie DUPONT Frères Rive Gauche'), 'Boulangerie DUPONT Frères Rive…');
  for (const title of ['MARTIN Claire — Dommages structure', 'Priya Patel — Term Life $1M', 'E0FF1B47']) {
    assert.equal(compact(title), title.replace(' — ', ' · '));
  }
  assert.deepEqual(compactApplicationTitle('LECOMTE Sandrine'), {
    holder: 'LECOMTE Sandrine',
    subject: null,
    text: 'LECOMTE Sandrine',
  });
});

test('amounts follow the claim currency (CHF in Switzerland) and the UI language', () => {
  const { applicationCurrency, formatAmount } = currency;
  assert.equal(applicationCurrency({ jurisdiction: { country: 'CH', currency: 'CHF' } }), 'CHF');
  assert.equal(applicationCurrency({ jurisdiction: { country: 'FR', currency: 'EUR' } }), 'EUR');
  assert.equal(applicationCurrency({}), 'EUR');
  assert.equal(applicationCurrency(null), 'EUR');

  for (const locale of locales) {
    const chf = formatAmount(1697400, 'CHF', locale, { maximumFractionDigits: 0 });
    assert.match(chf, /CHF/);
    assert.match(chf, /1.697.400/);
    assert.doesNotMatch(chf, /€/);
  }
  assert.match(formatAmount(6560, 'EUR', 'fr', { maximumFractionDigits: 0 }), /6\s?560\s?€/);
  assert.equal(formatAmount(6560, 'EUR', 'en', { maximumFractionDigits: 0 }), '€6,560');
});

test('model findings are filed under a theme in English, French and German', () => {
  const { classifyTheme } = signals;
  assert.equal(classifyTheme('Possibly AI-generated image'), 'photos');
  assert.equal(classifyTheme('Insufficient statement consistency'), 'statement');
  assert.equal(classifyTheme('Chronology to be clarified'), 'timeline');
  assert.equal(classifyTheme('Weather cause not confirmed'), 'cover');
  assert.equal(classifyTheme('Estimated amount to be recontextualized'), 'amount');
  assert.equal(classifyTheme('Exclusions / cover to be checked'), 'policy');
  assert.equal(classifyTheme('Cohérence de la déclaration insuffisante'), 'statement');
  assert.equal(classifyTheme('Montant estimé à recontextualiser'), 'amount');
  assert.equal(classifyTheme('Möglicherweise KI-generiertes Bild'), 'photos');
  assert.equal(classifyTheme('Wetterursache nicht bestätigt'), 'cover');
  assert.equal(classifyTheme('Ausschlüsse und Deckung prüfen'), 'policy');
  assert.equal(classifyTheme('Electrical damage pattern may reflect chronic moisture'), 'fraud');
});

test('duplicate facts merge into one ranked signal that keeps every source', () => {
  const merged = signals.mergeSignals([
    { theme: 'amount', severity: 'warning', title: 'High amount', detail: '€6,560 > €5,000', sources: ['rule'] },
    { theme: 'cover', severity: 'warning', title: 'Weather event', detail: 'Not confirmed', sources: ['rule'] },
    { theme: 'photos', severity: 'critical', title: '1 suspicious photo', detail: '22%', sources: ['photoAnalysis'] },
    { theme: 'cover', severity: 'critical', title: 'Storm not confirmed', detail: '8 sources', sources: ['webIq'], tab: 'web' },
    { theme: 'amount', severity: 'warning', title: 'Amount to recontextualize', detail: 'LLM', sources: ['fraudModel'] },
    { theme: 'fraud', severity: 'warning', title: 'Chronic moisture', detail: 'a', sources: ['fraudModel'] },
    { theme: 'fraud', severity: 'warning', title: 'Infiltration path not evidenced', detail: 'b', sources: ['fraudModel'] },
  ]);

  assert.deepEqual(merged.map((s) => s.title), [
    '1 suspicious photo',
    'Storm not confirmed',
    'High amount',
    'Chronic moisture',
    'Infiltration path not evidenced',
  ]);
  const cover = merged.find((s) => s.theme === 'cover');
  assert.equal(cover.severity, 'critical');
  assert.deepEqual(cover.sources, ['rule', 'webIq']);
  assert.deepEqual(cover.merged, ['Weather event']);
  assert.equal(cover.tab, 'web');
  const amount = merged.find((s) => s.theme === 'amount');
  assert.deepEqual(amount.merged, ['Amount to recontextualize']);
  assert.deepEqual(amount.sources, ['rule', 'fraudModel']);
  assert.equal(new Set(merged.map((s) => s.id)).size, merged.length);
});

test('essential view shows important signals first and hides information-only ones', () => {
  const merged = signals.mergeSignals([
    { theme: 'customer', severity: 'info', title: 'Urgency', detail: '', sources: ['rule'] },
    { theme: 'photos', severity: 'critical', title: 'Photo', detail: '', sources: ['photoAnalysis'] },
    { theme: 'documents', severity: 'warning', title: 'Missing estimate', detail: '', sources: ['rule'] },
  ]);
  const { shown, hidden } = signals.splitEssential(merged, 5);
  assert.deepEqual(shown.map((s) => s.title), ['Photo', 'Missing estimate']);
  assert.deepEqual(hidden.map((s) => s.title), ['Urgency']);
  assert.deepEqual(signals.countByFilter(merged), { all: 3, fraud: 1, cover: 0, amount: 0, documents: 1, customer: 1 });
});

test('latest updates are ordered and only new since the previous visit', () => {
  const list = updates.collectCaseUpdates({
    created_at: '2026-10-16T13:53:34Z',
    files: [1, 2, 3],
    extracted_fields: { a: 1, b: 2 },
    orchestration: {
      stages: { extraction: { completed_at: '2026-10-16T13:55:11Z' }, analysis: { completed_at: '2026-10-16T13:57:41Z' } },
      review: { status: 'needs_review' },
    },
    sentiment_analysis: { computed_at: '2026-10-16T13:57:46Z', level: 'critical', score: 88 },
    fraud_analysis: {
      analysis_timestamp: '2026-10-16T15:01:43Z',
      overall_assessment: { overall_fraud_risk: 'HIGH', risk_score: 0.79, siu_referral_recommended: true },
      web_intelligence: { event_verified: false, source_urls: ['a', 'b'] },
    },
    action_history: [{ action_id: 'x', label: 'Decision: deferred', at: 'not a date', decision: 'defer' }],
  });

  assert.deepEqual(list.map((u) => u.kind), ['fraud', 'webCheck', 'sentiment', 'analysis', 'extraction', 'created']);
  assert.deepEqual(list[0].params, { band: 'HIGH', score: 79, siu: 1 });
  assert.deepEqual(list[1].params, { verdict: 'notConfirmed', sources: 2 });
  assert.deepEqual(list[3].params, { review: 1 });
  const previousVisit = Date.parse('2026-10-16T14:00:00Z');
  assert.deepEqual(list.filter((u) => updates.isNewSince(u, previousVisit)).map((u) => u.kind), ['fraud', 'webCheck']);
  assert.equal(list.some((u) => updates.isNewSince(u, null)), false);
});

test('AI pipeline stays quiet when fine and flags review or real problems', () => {
  assert.equal(health.pipelineHealth({}).status, 'ok');
  const review = health.pipelineHealth({
    orchestration: { review: { status: 'needs_review', reasons: [{ code: 'unverified_llm_fields' }] } },
  });
  assert.deepEqual([review.status, review.reasons], ['review', ['unverified_llm_fields']]);
  const problem = health.pipelineHealth({
    orchestration: {
      stages: { analysis: { budget_exhausted: true } },
      review: { status: 'needs_review', reasons: [{ code: 'low_confidence' }, { code: 'analysis_errors' }] },
    },
  });
  assert.deepEqual([problem.status, problem.reasons], ['problem', ['analysis_errors', 'low_confidence']]);
  const fallback = health.pipelineHealth({ extraction_provenance: { summary: { fallback_used: true, fallback_reason: 'cu_timeout' } } });
  assert.deepEqual([fallback.status, fallback.fallbackReason], ['review', 'cu_timeout']);
  const reviewedFallback = health.pipelineHealth({
    extraction_provenance: { summary: { fallback_used: true, fallback_reason: 'cu_timeout' } },
    orchestration: { review: { status: 'reviewed' } },
  });
  assert.equal(reviewedFallback.status, 'ok');
  assert.equal(health.pipelineHealth({ orchestration: { review: { status: 'reviewed' } } }).status, 'ok');
});

test('recommendations map to real decisions and never invent a confidence score', () => {
  const t = (key, values) => (values ? `${key}:${JSON.stringify(values)}` : key);
  const base = { analysisComplete: true, fraudRisk: 0.1, siuRecommended: false, inconsistentStatement: false, amount: 1200, amountLabel: '1,200', thresholdLabel: '5,000' };

  assert.equal(recommendation.buildRecommendation({ ...base, analysisComplete: false }, t), null);
  const siu = recommendation.buildRecommendation({ ...base, siuRecommended: true, fraudRisk: 0.79 }, t);
  assert.deepEqual([siu.id, siu.decision, siu.tone, siu.taskKey], ['escalate_siu', 'defer', 'critical', 'siu_referral']);
  assert.deepEqual([siu.title, siu.reason], ['labels.escalate_siu', 'reasoning.siu_default']);
  assert.equal('confidence' in siu, false);
  assert.equal(recommendation.buildRecommendation({ ...base, fraudRisk: 0.65 }, t).id, 'request_expertise');
  const expert = recommendation.buildRecommendation({ ...base, amount: 6560, amountLabel: '6,560' }, t);
  assert.deepEqual([expert.id, expert.decision], ['approve_with_expertise', 'approve_with_conditions']);
  assert.match(expert.reason, /6,560/);
  assert.deepEqual(
    [recommendation.buildRecommendation(base, t).id, recommendation.buildRecommendation(base, t).decision],
    ['stp_approve', 'approve'],
  );
  assert.equal(recommendation.buildRecommendation({ ...base, fraudRisk: 0.4 }, t).id, 'approve_standard');
});

test('recommendation reasons keep CHF and EUR consistent with the amount and expertise threshold', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const t = createTranslator({ locale, messages, namespace: 'nextAction' });
    for (const code of ['CHF', 'EUR']) {
      const money = value => currency.formatAmount(value, code, locale, { maximumFractionDigits: 0 });
      for (const amount of [1200, 1697400]) {
        const result = recommendation.buildRecommendation({
          analysisComplete: true, fraudRisk: 0.1, siuRecommended: false,
          inconsistentStatement: false, amount, amountLabel: money(amount),
          thresholdLabel: money(5000),
        }, t);
        assert.ok(result.reason.includes(money(amount)), `${locale}/${code}: amount`);
        if (amount > 5000) {
          assert.ok(result.reason.includes(money(5000)), `${locale}/${code}: threshold`);
        }
        assert.doesNotMatch(result.reason, code === 'CHF' ? /€|EUR/ : /CHF/);
        assert.doesNotMatch(result.reason, /\{(?:amount|threshold)\}/);
      }
    }
  }
});

test('property amount signals render the claim currency on both sides of the expertise threshold', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const t = createTranslator({ locale, messages, namespace: 'claims' });
    const tc = createTranslator({ locale, messages, namespace: 'caseCockpit' });
    for (const code of ['CHF', 'EUR']) {
      const money = value => currency.formatAmount(value, code, locale, { maximumFractionDigits: 0 });
      for (const amount of [4999, 5000, 5001, 1697400]) {
        const result = propertySignals.buildPropertySignals({
          fraud: null, amount, amountLabel: money(amount), thresholdLabel: money(5000),
          overclaim: null, nature: '', thirdParty: '', urgency: '', preexisting: '',
          description: '', llmOutputs: {}, fileNames: [],
        }, t, tc).find(signal => signal.theme === 'amount');
        assert.equal(!!result, amount > 5000);
        if (result) {
          assert.ok(result.detail.includes(money(amount)), `${locale}/${code}: amount`);
          assert.ok(result.detail.includes(money(5000)), `${locale}/${code}: threshold`);
          assert.doesNotMatch(result.detail, code === 'CHF' ? /€|EUR|euros?/i : /CHF/);
          assert.doesNotMatch(result.detail, /\{(?:amount|threshold)\}/);
        }
      }
    }
  }
});

test('Swiss weather signals refer to AVB rather than the French Cat-Nat order independently of currency', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const t = createTranslator({ locale, messages, namespace: 'claims' });
    const tc = createTranslator({ locale, messages, namespace: 'caseCockpit' });
    for (const country of ['CH', 'ch', 'FR', undefined]) {
      for (const code of ['CHF', 'EUR']) {
        const result = propertySignals.buildPropertySignals({
          fraud: null, amount: 0, amountLabel: code, thresholdLabel: code, country,
          overclaim: null, nature: 'hail', thirdParty: '', urgency: '', preexisting: '',
          description: '', llmOutputs: {}, fileNames: [],
        }, t, tc).find(signal => signal.theme === 'cover');
        assert.equal(result.detail, messages.claims.signals[
          country?.toUpperCase() === 'CH' ? 'weatherEventDetailCh' : 'weatherEventDetail'
        ]);
        if (country?.toUpperCase() === 'CH') assert.match(result.detail, /AVB/);
      }
    }
  }
});

test('Aurora mode details stay in administration while client outlook labels remain neutral', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const demo = createTranslator({locale, messages, namespace: 'auroraDemo'});
    for (const key of ['title', 'notice', 'confirm', 'scenario', 'saveHelp', 'billing']) {
      assert.ok(demo(key).length > 5);
      assert.notEqual(demo(key), `auroraDemo.${key}`);
    }
    assert.ok(demo('validated', {admin: 'test-admin', at: '2026-11-08'}).includes('test-admin'));
    for (const id of ['swiss-chocolate-storm', 'swiss-watch-storm', 'wine-cellar']) {
      assert.notEqual(demo(`scenarios.${id}`), `auroraDemo.scenarios.${id}`);
    }
    const admin = messages.adminPanel.aurora;
    for (const key of ['demo_scenario', 'demo_contract', 'demo_audit']) {
      assert.equal(typeof admin.checklist.items[key], 'string');
    }
    assert.equal(typeof messages.caseCockpit.aurora.summary.demo_simulation, 'string');
    assert.match(demo('guide'), /simulat/i);
    assert.ok(demo('presentation').length > 20);
    assert.ok(!messages.demoGuide.claimsNavigation.includes(demo('guide')));
    const outlook = createTranslator({locale, messages, namespace: 'caseCockpit.aurora.scenario'});
    for (const key of ['run', 'running', 'refresh', 'description', 'chartLabel', 'timelineBoundary']) {
      assert.doesNotMatch(outlook(key), /demo|démo|simulat|synthe|synthé/i);
    }
  }
});

test('Aurora wording supports historical inputs rather than promising current weather', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const t = createTranslator({ locale, messages, namespace: 'caseCockpit.aurora' });
    const result = t('result', { model: 'aurora-0.25-v1.5', hours: 6 });
    assert.ok(result.includes('aurora-0.25-v1.5'));
    assert.ok(result.includes('6'));
    assert.doesNotMatch(result, /next|prochaines|nächsten/);
    assert.match(t('description'), /histor/i);
    assert.equal(typeof t('evidence.initialConditions'), 'string');
  }
});

test('Aurora availability and backend-only diagnostics are localized without inventing a Blob cause', () => {
  for (const locale of locales) {
    const messages = messagesFor(locale);
    const t = createTranslator({ locale, messages, namespace: 'caseCockpit.aurora' });
    for (const key of ['unavailable', 'disabled', 'blobAccessDenied', 'loadingStatus', 'locationRequired']) {
      assert.equal(typeof messages.caseCockpit.aurora[key], 'string', `${locale}.${key}`);
      assert.notEqual(t(key), `caseCockpit.aurora.${key}`);
    }
    assert.doesNotMatch(t('disabled'), /403|Blob/);
    assert.match(t('blobAccessDenied'), /403/);
    const admin = messages.adminPanel.aurora;
    assert.match(admin.testScope, /PrevaIQ/);
    for (const operation of [
      'acquire_endpoint_credential', 'endpoint_task_info',
      'download_initial_condition', 'get_user_delegation_key',
    ]) {
      assert.equal(typeof admin.diagnostics.operations[operation], 'string');
    }
  }
});

test('every dynamic cockpit key exists in English, French and German', () => {
  const lookup = (messages, key) =>
    key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), messages);

  const keys = [
    ...['critical', 'warning', 'info'].map((value) => `caseCockpit.severity.${value}`),
    ...Object.keys(signals.THEME_TAB).map((theme) => `caseCockpit.themes.${theme}`),
    ...['photoAnalysis', 'declarationCheck', 'fraudModel', 'webIq', 'policy', 'rule', 'fileDates', 'aiAnalysis']
      .map((source) => `caseCockpit.sources.${source}`),
    ...['all', 'fraud', 'cover', 'amount', 'documents', 'customer'].map((filter) => `caseCockpit.attention.filters.${filter}`),
    ...['essential', 'detailed'].map((density) => `caseCockpit.attention.density.${density}`),
    ...['summary', 'fraud', 'web', 'cover', 'evidence', 'customer', 'timeline', 'data', 'pipeline']
      .map((tab) => `caseCockpit.drawer.tabs.${tab}`),
    ...['authentic', 'doubtful', 'suspicious'].map((badge) => `caseCockpit.evidence.badge.${badge}`),
    ...['calm', 'moderate', 'stressed', 'critical'].map((level) => `caseCockpit.kpi.customerLevels.${level}`),
    ...['LOW', 'MODERATE', 'HIGH'].map((band) => `caseCockpit.updates.bands.${band}`),
    ...['confirmed', 'notConfirmed', 'unclear', 'skipped'].flatMap((verdict) => [
      `caseCockpit.updates.kinds.web.${verdict}`,
      `caseCockpit.webTab.verdict.${verdict}`,
    ]),
    ...['ok', 'review', 'problem'].map((status) => `workbench.pipelineState.${status}`),
    ...coverageView.COVERAGE_TONES.map((tone) => `caseCockpit.coverTab.tone.${tone}`),
    ...coverageView.PERIL_KEYS.map((peril) => `caseCockpit.coverTab.perils.${peril}`),
    ...['deductible', 'catNat', 'irsi', 'expertise', 'recourse'].map((rule) => `caseCockpit.coverTab.rule.${rule}`),
    ...['applies', 'notApplicable', 'required', 'notRequired', 'possible', 'notPossible', 'unknown']
      .map((answer) => `caseCockpit.coverTab.ruleValue.${answer}`),
  ];

  // Every recommendation (and alternative) the rules can produce, as translation keys.
  const t = (key) => `nextAction.${key}`;
  const base = { analysisComplete: true, fraudRisk: 0.1, siuRecommended: false, inconsistentStatement: false, amount: 1200, amountLabel: '1,200', thresholdLabel: '5,000' };
  const inputs = [
    { siuRecommended: true },
    { fraudRisk: 0.65 },
    { inconsistentStatement: true },
    { amount: 6560 },
    {},
    { fraudRisk: 0.4 },
  ];
  for (const input of inputs) {
    const result = recommendation.buildRecommendation({ ...base, ...input }, t);
    for (const option of [result, ...result.alternatives]) keys.push(option.title, option.reason);
  }

  for (const locale of locales) {
    const messages = messagesFor(locale);
    const missing = keys.filter((key) => typeof lookup(messages, key) !== 'string');
    assert.deepEqual(missing, [], `${locale} is missing cockpit keys`);
  }
});
