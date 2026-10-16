"""Create insurance business data tables and seed with demo data.

Creates clients, polices, sinistres, paiements, prets tables in workbenchiq
schema with coherent data matching the 34 seeded application dossiers.
Every row cross-references Customer 360 PRV-xxx IDs and app-xxx dossier IDs.

Usage:
    python scripts/setup_business_tables.py

Env vars: POSTGRESQL_HOST, POSTGRESQL_USER, POSTGRESQL_PASSWORD,
          POSTGRESQL_DATABASE, DATABASE_BACKEND=postgresql
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")
from app.database.pool import init_pool, get_pool
from app.config import load_settings

# ── Table DDL ─────────────────────────────────────────────────────────────

CLIENTS_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.clients (
    client_id VARCHAR(20) PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    date_naissance DATE,
    adresse VARCHAR(255),
    ville VARCHAR(100),
    code_postal VARCHAR(10),
    telephone VARCHAR(20),
    email VARCHAR(150),
    segment VARCHAR(50),
    risk_tier VARCHAR(20),
    date_creation DATE NOT NULL,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

POLICES_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.polices (
    police_id VARCHAR(30) PRIMARY KEY,
    client_id VARCHAR(20) NOT NULL REFERENCES workbenchiq.clients(client_id),
    type_police VARCHAR(50) NOT NULL,
    produit VARCHAR(100) NOT NULL,
    numero_contrat VARCHAR(30),
    date_effet DATE NOT NULL,
    date_expiration DATE,
    prime_annuelle NUMERIC(12,2),
    franchise NUMERIC(10,2),
    plafond_garantie NUMERIC(14,2),
    statut VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SINISTRES_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.sinistres (
    sinistre_id VARCHAR(30) PRIMARY KEY,
    police_id VARCHAR(30) NOT NULL REFERENCES workbenchiq.polices(police_id),
    client_id VARCHAR(20) NOT NULL REFERENCES workbenchiq.clients(client_id),
    application_id VARCHAR(50),
    type_sinistre VARCHAR(50) NOT NULL,
    date_sinistre DATE NOT NULL,
    date_declaration DATE NOT NULL,
    description TEXT,
    montant_reclame NUMERIC(12,2),
    montant_accepte NUMERIC(12,2),
    montant_paye NUMERIC(12,2),
    statut VARCHAR(30) DEFAULT 'ouvert',
    responsabilite VARCHAR(30),
    taux_responsabilite_assure INT DEFAULT 0,
    risque_fraude VARCHAR(20),
    agent_assignation VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

PAIEMENTS_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.paiements (
    paiement_id VARCHAR(30) PRIMARY KEY,
    sinistre_id VARCHAR(30) NOT NULL REFERENCES workbenchiq.sinistres(sinistre_id),
    client_id VARCHAR(20) NOT NULL REFERENCES workbenchiq.clients(client_id),
    montant NUMERIC(12,2) NOT NULL,
    type_paiement VARCHAR(30) NOT NULL,
    date_paiement DATE NOT NULL,
    reference VARCHAR(50),
    statut VARCHAR(20) DEFAULT 'effectue',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

PRETS_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.prets (
    pret_id VARCHAR(30) PRIMARY KEY,
    client_id VARCHAR(20) NOT NULL REFERENCES workbenchiq.clients(client_id),
    application_id VARCHAR(50),
    type_pret VARCHAR(50) NOT NULL,
    montant_pret NUMERIC(14,2) NOT NULL,
    valeur_bien NUMERIC(14,2),
    ltv NUMERIC(5,2),
    taux_interet NUMERIC(5,3),
    duree_mois INT,
    mensualite NUMERIC(10,2),
    ratio_gds NUMERIC(5,2),
    ratio_tds NUMERIC(5,2),
    score_credit INT,
    statut VARCHAR(30) DEFAULT 'approuve',
    date_demande DATE NOT NULL,
    date_decision DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

# ── Seed: Clients (all PRV-xxx used by dossiers) ─────────────────────────

SEED_CLIENTS = """
INSERT INTO workbenchiq.clients (client_id, nom, prenom, date_naissance, adresse, ville, code_postal, telephone, email, segment, risk_tier, date_creation, tags) VALUES
('PRV-001', 'MERTENS LAFFITE', 'Olivier', '1985-02-14', '12 Rue du Château', 'Paris', '75004', '+33 6 12 00 00 01', 'olivier.mertens@email.fr', 'particulier', 'medium', '2019-05-01', ARRAY['habitation','cave-à-vins','sinistre-récent']),
('PRV-003', 'BERNARD', 'Thomas', '1990-11-05', '9 Avenue Foch', 'Marseille', '13001', '+33 6 33 22 11 00', 'thomas.bernard@email.fr', 'particulier', 'low', '2021-07-22', ARRAY['jeune-conducteur','auto']),
('PRV-004', 'PETIT', 'Sophie', '1968-08-30', '22 Rue Pasteur', 'Aix-en-Provence', '13100', '+33 6 77 88 99 00', 'sophie.petit@email.fr', 'particulier', 'low', '2019-09-20', ARRAY['santé','fidèle','retraitée']),
('PRV-005', 'LEROY', 'Jean-Marc', '1985-04-18', '17 Rue de la Liberté', 'Dijon', '21000', '+33 6 45 67 89 01', 'jeanmarc.leroy@email.fr', 'particulier', 'medium', '2020-02-10', ARRAY['habitation','dégâts-des-eaux']),
('PRV-006', 'MOREAU', 'Isabelle', '1972-12-03', '11 Rue Victor Hugo', 'Paris', '75008', '+33 6 44 55 66 77', 'isabelle.moreau@email.fr', 'particulier', 'low', '2020-11-05', ARRAY['multi-contrats','santé','vie']),
('PRV-007', 'GARCIA', 'Antonio', '1988-06-21', '14 Rue des Lilas', 'Toulouse', '31000', '+33 6 12 34 56 78', 'antonio.garcia@email.fr', 'particulier', 'high', '2020-03-15', ARRAY['sinistre-auto','récidive']),
('PRV-008', 'MARTIN', 'Claire', '1995-02-14', '5 Place Bellecour', 'Lyon', '69002', '+33 6 90 12 34 56', 'claire.martin@email.fr', 'particulier', 'low', '2024-01-10', ARRAY['nouveau-client','habitation']),
('PRV-009', 'DUBOIS', 'Philippe', '1960-09-28', '5 Place du Marché', 'Strasbourg', '67000', '+33 6 11 22 33 44', 'philippe.dubois@email.fr', 'particulier', 'medium', '2017-06-10', ARRAY['fidèle','santé','chronique']),
('PRV-010', 'LEFEBVRE', 'Nathalie', '1979-01-07', '27 Rue Gambetta', 'Lille', '59000', '+33 6 88 99 00 11', 'nathalie.lefebvre@email.fr', 'particulier', 'low', '2018-04-18', ARRAY['auto','habitation']),
('PRV-011', 'ROUX', 'Frédéric', '1983-05-11', '3 Rue de la Gare', 'Bordeaux', '33000', '+33 6 22 33 44 55', 'frederic.roux@email.fr', 'particulier', 'medium', '2022-09-01', ARRAY['habitation','auto']),
('PRV-012', 'FOURNIER', 'Camille', '1992-10-25', '8 Rue des Capucins', 'Mérignac', '33700', '+33 6 78 90 12 34', 'camille.fournier@email.fr', 'particulier', 'low', '2021-06-15', ARRAY['santé','auto']),
('PRV-013', 'GIRARD', 'Laurent', '1970-07-04', '40 Rue Principale', 'Annecy', '74000', '+33 6 56 78 90 12', 'laurent.girard@email.fr', 'particulier', 'medium', '2018-09-01', ARRAY['habitation','sinistre-habitation','tempête']),
('PRV-014', 'BONNET', 'Véronique', '1966-04-19', '15 Avenue de Royat', 'Clermont-Ferrand', '63000', '+33 6 34 56 78 90', 'veronique.bonnet@email.fr', 'particulier', 'low', '2016-03-20', ARRAY['fidèle','vie','épargne']),
('PRV-015', 'LAMBERT', 'Sébastien', '1987-08-08', '23 Allée des Violettes', 'Toulouse', '31400', '+33 6 67 89 01 23', 'sebastien.lambert@email.fr', 'particulier', 'high', '2023-05-01', ARRAY['sinistre-habitation','fraude-suspectée']),
('PRV-016', 'FONTAINE', 'Aurélie', '1993-12-31', '33 Rue de la Paix', 'Lyon', '69003', '+33 6 66 77 88 99', 'aurelie.fontaine@email.fr', 'particulier', 'low', '2022-02-14', ARRAY['santé','jeune']),
('PRV-017', 'ROUSSEAU', 'Marc', '1958-03-15', '8 Avenue de la République', 'Lyon', '69003', '+33 6 98 76 54 32', 'marc.rousseau@email.fr', 'particulier', 'medium', '2018-01-10', ARRAY['fidèle','santé','hospitalisation']),
('PRV-018', 'VINCENT', 'Émilie', '1991-06-27', '12 Bd de la Croisette', 'Nice', '06400', '+33 6 45 67 89 02', 'emilie.vincent@email.fr', 'particulier', 'low', '2021-03-15', ARRAY['auto','habitation','côte-d-azur']),
('PRV-019', 'MULLER', 'Hans', '1976-11-12', '4 Rue des Vosges', 'Saint-Louis', '68300', '+33 6 79 01 23 45', 'hans.muller@email.fr', 'particulier', 'low', '2019-08-20', ARRAY['frontalier','multi-contrats']),
('PRV-020', 'LECOMTE', 'Sandrine', '1984-09-03', '10 Chemin de Falgarde', 'Albi', '81000', '+33 6 89 01 23 45', 'sandrine.lecomte@email.fr', 'particulier', 'medium', '2020-04-01', ARRAY['habitation','cave','inondation']),
('PRV-022', 'CHEVALIER', 'Julie', '1997-05-09', '30 Rue des Étudiants', 'Rennes', '35000', '+33 6 01 23 45 67', 'julie.chevalier@email.fr', 'particulier', 'low', '2024-09-01', ARRAY['nouveau-client','auto','étudiant']),
('PRV-023', 'RENARD', 'Christophe', '1973-08-17', 'Zone Artisanale Nord', 'Limoges', '87000', '+33 6 12 34 56 90', 'christophe.renard@email.fr', 'professionnel', 'medium', '2019-02-01', ARRAY['flotte-auto','professionnel']),
('PRV-024', 'LEMAIRE', 'Sylvie', '1969-01-28', '7 Rue de Passy', 'Paris', '75016', '+33 6 23 45 67 89', 'sylvie.lemaire@email.fr', 'particulier', 'low', '2017-10-15', ARRAY['habitation','santé','fidèle']),
('PRV-025', 'ARNAUD', 'Thierry', '1980-04-02', '45 Boulevard Voltaire', 'Paris', '75011', '+33 6 55 44 33 22', 'thierry.arnaud@email.fr', 'particulier', 'high', '2023-08-01', ARRAY['sinistre-multiple','auto','habitation']),
('PRV-026', 'PICARD', 'Delphine', '1994-07-23', '18 Cours Jean Jaurès', 'Grenoble', '38000', '+33 6 34 56 78 12', 'delphine.picard@email.fr', 'particulier', 'low', '2022-05-01', ARRAY['santé','optique','dentaire']),
('PRV-028', 'SCHMITT', 'Éric', '1978-10-14', '6 Rue du Vignoble', 'Colmar', '68000', '+33 6 56 78 90 34', 'eric.schmitt@email.fr', 'particulier', 'medium', '2019-01-15', ARRAY['habitation','grêle','toiture']),
('PRV-029', 'BLANCHARD', 'Stéphanie', '1986-03-06', '41 Avenue de Bretagne', 'Angers', '49000', '+33 6 99 88 77 66', 'stephanie.blanchard@email.fr', 'particulier', 'low', '2022-06-01', ARRAY['auto','habitation','famille']),
('PRV-030', 'DA SILVA', 'Carlos', '1981-12-09', '22 Rue Jean Moulin', 'Rennes', '35000', '+33 6 78 90 12 56', 'carlos.dasilva@email.fr', 'particulier', 'medium', '2021-11-01', ARRAY['habitation','dégâts-des-eaux','locataire']),
('PRV-SC',  'CHEN', 'Sarah', '1988-03-15', '42 Maple Grove Ave', 'Toronto', 'M4C1L8', '(416) 555-0142', 'sarah.chen@email.com', 'particulier', 'low', '2019-06-01', ARRAY['long-term','multi-product','preferred']),
('PRV-MW',  'WILLIAMS', 'Marcus', '1980-07-28', '18 Oak Street', 'Vancouver', 'V6K2E4', '(604) 555-0387', 'marcus.williams@email.com', 'particulier', 'medium', '2020-01-15', ARRAY['hypertension','cardiac-history']),
('PRV-PP',  'PATEL', 'Priya', '1987-04-10', '7 Cedar Lane', 'Montreal', 'H3B2Y7', '(514) 555-0219', 'priya.patel@email.com', 'particulier', 'low', '2021-03-01', ARRAY['multi-product','tech-professional']),
('PRV-002', 'DUPONT', 'Marie', '1975-03-22', '16 Rue des Roses', 'Paris', '75011', '+33 6 55 66 77 88', 'marie.dupont@email.fr', 'particulier', 'low', '2015-07-10', ARRAY['fidèle','multi-contrats','auto+habitation']),
('PRV-035', 'DUPONT', 'Marie', '1992-04-05', '16 Rue des Roses', 'Rennes', '35000', '+33 6 55 66 77 89', 'marie.dupont35@email.fr', 'particulier', 'low', '2023-01-15', ARRAY['hypothécaire','primo-accédant'])
ON CONFLICT (client_id) DO NOTHING;
"""

# ── Seed: Polices ─────────────────────────────────────────────────────────

SEED_POLICES = """
INSERT INTO workbenchiq.polices (police_id, client_id, type_police, produit, numero_contrat, date_effet, date_expiration, prime_annuelle, franchise, plafond_garantie, statut) VALUES
-- Auto
('POL-AUTO-007', 'PRV-007', 'auto', 'PrevaIQ Auto Tous Risques', 'GA-2020-31-0078', '2020-04-01', '2026-04-01', 890.00, 300.00, 50000.00, 'active'),
('POL-AUTO-025', 'PRV-025', 'auto', 'PrevaIQ Auto Tous Risques', 'GA-2023-75-0125', '2023-09-01', '2026-09-01', 1250.00, 500.00, 50000.00, 'active'),
('POL-AUTO-003', 'PRV-003', 'auto', 'PrevaIQ Auto Tiers+', 'GA-2021-13-0089', '2021-08-01', '2026-08-01', 650.00, 400.00, 30000.00, 'active'),
('POL-AUTO-010', 'PRV-010', 'auto', 'PrevaIQ Auto Tous Risques', 'GA-2018-59-0045', '2018-05-01', '2026-05-01', 780.00, 300.00, 50000.00, 'active'),
('POL-AUTO-011', 'PRV-011', 'auto', 'PrevaIQ Auto Essentiel', 'GA-2022-33-0067', '2022-10-01', '2026-10-01', 520.00, 500.00, 25000.00, 'active'),
('POL-AUTO-018', 'PRV-018', 'auto', 'PrevaIQ Auto Tous Risques', 'GA-2021-06-0098', '2021-04-01', '2026-04-01', 720.00, 300.00, 50000.00, 'active'),
('POL-AUTO-012', 'PRV-012', 'auto', 'PrevaIQ Auto Tiers', 'GA-2021-33-0112', '2021-07-01', '2026-07-01', 380.00, 600.00, 15000.00, 'active'),
('POL-AUTO-023', 'PRV-023', 'auto', 'PrevaIQ Flotte Pro 5+', 'GA-2019-87-0034', '2019-03-01', '2026-03-01', 4200.00, 500.00, 150000.00, 'active'),
-- Santé
('POL-SANTE-017', 'PRV-017', 'sante', 'PrevaIQ Complémentaire Santé+', 'GS-2018-69-0034', '2018-02-01', '2026-02-01', 1850.00, 0.00, 100000.00, 'active'),
('POL-SANTE-004', 'PRV-004', 'sante', 'PrevaIQ Santé Sérénité', 'GS-2008-13-0012', '2008-10-01', '2026-10-01', 1200.00, 0.00, 80000.00, 'active'),
('POL-SANTE-009', 'PRV-009', 'sante', 'PrevaIQ Complémentaire Santé+', 'GS-2017-67-0023', '2017-07-01', '2026-07-01', 2100.00, 0.00, 100000.00, 'active'),
('POL-SANTE-016', 'PRV-016', 'sante', 'PrevaIQ Complémentaire Santé', 'GS-2022-69-0089', '2022-03-01', '2026-03-01', 950.00, 0.00, 60000.00, 'active'),
('POL-SANTE-006', 'PRV-006', 'sante', 'PrevaIQ Santé Plus', 'GS-2020-75-0078', '2020-12-01', '2026-12-01', 2400.00, 0.00, 120000.00, 'active'),
('POL-SANTE-026', 'PRV-026', 'sante', 'PrevaIQ Complémentaire Santé', 'GS-2022-38-0102', '2022-06-01', '2026-06-01', 680.00, 0.00, 50000.00, 'active'),
('POL-SANTE-024', 'PRV-024', 'sante', 'PrevaIQ Santé Plus', 'GS-2017-75-0056', '2017-11-01', '2026-11-01', 1650.00, 0.00, 100000.00, 'active'),
('POL-SANTE-012', 'PRV-012', 'sante', 'PrevaIQ Complémentaire Santé', 'GS-2021-33-0098', '2021-07-01', '2026-07-01', 750.00, 0.00, 60000.00, 'active'),
-- Vie
('POL-VIE-SC', 'PRV-SC', 'vie', 'Term Life Insurance 20Y', 'GL-2019-ON-0042', '2019-07-01', '2039-07-01', 510.00, 0.00, 500000.00, 'active'),
('POL-VIE-MW', 'PRV-MW', 'vie', 'Whole Life Insurance', 'GL-2020-BC-0015', '2020-02-01', NULL, 1450.00, 0.00, 750000.00, 'active'),
('POL-VIE-PP', 'PRV-PP', 'vie', 'Universal Life Insurance', 'GL-2021-QC-0031', '2021-04-01', NULL, 980.00, 0.00, 1000000.00, 'active'),
-- Habitation
('POL-HAB-001', 'PRV-001', 'habitation', 'PrevaIQ Habitation Confort', 'GH-2019-75-0012', '2019-06-01', '2026-06-01', 680.00, 250.00, 200000.00, 'active'),
('POL-HAB-013', 'PRV-013', 'habitation', 'PrevaIQ Habitation Essentiel', 'GH-2018-74-0034', '2018-10-01', '2026-10-01', 520.00, 300.00, 150000.00, 'active'),
('POL-HAB-005', 'PRV-005', 'habitation', 'PrevaIQ Habitation Confort', 'GH-2020-21-0045', '2020-03-01', '2026-03-01', 590.00, 250.00, 180000.00, 'active'),
('POL-HAB-015', 'PRV-015', 'habitation', 'PrevaIQ Habitation Essentiel', 'GH-2023-31-0067', '2023-06-01', '2026-06-01', 450.00, 300.00, 120000.00, 'active'),
('POL-HAB-020', 'PRV-020', 'habitation', 'PrevaIQ Habitation Confort+', 'GH-2020-81-0023', '2020-05-01', '2026-05-01', 720.00, 380.00, 220000.00, 'active'),
('POL-HAB-028', 'PRV-028', 'habitation', 'PrevaIQ Habitation Confort', 'GH-2019-68-0056', '2019-02-01', '2026-02-01', 640.00, 300.00, 190000.00, 'active'),
('POL-HAB-008', 'PRV-008', 'habitation', 'PrevaIQ Habitation Essentiel', 'GH-2024-69-0089', '2024-02-01', '2027-02-01', 420.00, 300.00, 130000.00, 'active'),
('POL-HAB-030', 'PRV-030', 'habitation', 'PrevaIQ Habitation Locataire', 'GH-2021-35-0078', '2021-12-01', '2026-12-01', 280.00, 150.00, 80000.00, 'active'),
-- Hypothécaire
('POL-HYP-SC', 'PRV-SC', 'hypothecaire', 'Assurance Emprunteur PrevaIQ', 'GE-2021-ON-0088', '2021-10-01', '2046-10-01', 1560.00, 0.00, 520000.00, 'active'),
('POL-HYP-MW', 'PRV-MW', 'hypothecaire', 'Assurance Emprunteur PrevaIQ', 'GE-2021-BC-0045', '2021-05-01', '2046-05-01', 1800.00, 0.00, 480000.00, 'active'),
('POL-HYP-PP', 'PRV-PP', 'hypothecaire', 'Assurance Emprunteur PrevaIQ', 'GE-2022-QC-0023', '2022-01-01', '2047-01-01', 1200.00, 0.00, 400000.00, 'active'),
('POL-HYP-002', 'PRV-002', 'hypothecaire', 'Assurance Emprunteur PrevaIQ', 'GE-2025-75-0115', '2025-08-01', '2050-08-01', 1350.00, 0.00, 450000.00, 'active'),
('POL-HYP-029', 'PRV-029', 'hypothecaire', 'Assurance Emprunteur PTZ', 'GE-2026-49-0034', '2026-04-01', '2051-04-01', 420.00, 0.00, 220000.00, 'active'),
('POL-HYP-014', 'PRV-014', 'hypothecaire', 'Assurance Emprunteur Rachat', 'GE-2025-63-0067', '2025-06-01', '2045-06-01', 540.00, 0.00, 180000.00, 'active'),
('POL-HYP-019', 'PRV-019', 'hypothecaire', 'Assurance Emprunteur PrevaIQ', 'GE-2026-68-0023', '2026-03-01', '2051-03-01', 1140.00, 0.00, 380000.00, 'active'),
('POL-HYP-035', 'PRV-035', 'hypothecaire', 'Assurance Emprunteur PTZ', 'GE-2023-35-0067', '2023-03-01', '2048-03-01', 420.00, 0.00, 220000.00, 'active')
ON CONFLICT (police_id) DO NOTHING;
"""

# ── Seed: Sinistres ───────────────────────────────────────────────────────

SEED_SINISTRES = """
INSERT INTO workbenchiq.sinistres (sinistre_id, police_id, client_id, application_id, type_sinistre, date_sinistre, date_declaration, description, montant_reclame, montant_accepte, montant_paye, statut, responsabilite, taux_responsabilite_assure, risque_fraude, agent_assignation) VALUES
-- Auto (8)
('SIN-AUTO-001', 'POL-AUTO-007', 'PRV-007', 'app-sc-auto-001', 'auto', '2024-11-15', '2024-11-18', 'Collision arrière feu rouge. Renault Clio V. Tiers MAIF identifié.', 1900.00, 1900.00, 1900.00, 'clos', 'tiers', 0, 'low', 'Dupont Marie'),
('SIN-AUTO-002', 'POL-AUTO-025', 'PRV-025', 'app-pp-auto-001', 'auto', '2025-01-22', '2025-01-23', 'BMW 320d — 3ème sinistre 2 mois. Incohérences photos.', 4500.00, 0.00, 0.00, 'investigation', 'na', 0, 'high', 'Lefranc Pascal'),
('SIN-AUTO-003', 'POL-AUTO-003', 'PRV-003', 'app-auto-003', 'auto', '2025-03-10', '2025-03-12', 'Accrochage parking. Peugeot 208. Rayure aile droite.', 980.00, 980.00, 580.00, 'clos', 'assure', 100, 'low', 'Martin Claire'),
('SIN-AUTO-004', 'POL-AUTO-010', 'PRV-010', 'app-auto-004', 'auto', '2025-06-05', '2025-06-06', 'Bris de glace pare-brise. Citroën C3 Aircross. Gravillons A1.', 620.00, 620.00, 620.00, 'clos', 'na', 0, 'low', 'Durand Paul'),
('SIN-AUTO-005', 'POL-AUTO-011', 'PRV-011', 'app-auto-005', 'auto', '2025-09-18', '2025-09-20', 'Vol VW Golf GTD retrouvé endommagé. Enquête SIU.', 4800.00, 0.00, 0.00, 'investigation', 'na', 0, 'high', 'Moreau Jean'),
('SIN-AUTO-006', 'POL-AUTO-018', 'PRV-018', 'app-auto-006', 'auto', '2025-08-14', '2025-08-16', 'Accrochage Promenade des Anglais. Toyota Yaris Cross.', 1350.00, 1350.00, 1350.00, 'clos', 'tiers', 0, 'low', 'Blanc Sophie'),
('SIN-AUTO-007', 'POL-AUTO-012', 'PRV-012', 'app-auto-007', 'auto', '2025-12-01', '2025-12-03', 'Document illisible — extraction échouée.', NULL, NULL, NULL, 'error', 'na', 0, 'low', NULL),
('SIN-AUTO-008', 'POL-AUTO-023', 'PRV-023', 'app-auto-008', 'auto', '2026-03-22', '2026-03-23', 'Flotte — Kangoo livraison collision marche arrière.', 1680.00, NULL, NULL, 'en_cours', 'assure', 100, 'low', 'Moreau Jean'),
-- Santé (8)
('SIN-SANTE-001', 'POL-SANTE-017', 'PRV-017', 'app-mw-hc-001', 'sante', '2025-02-10', '2025-02-15', 'PTG genou — Gonarthrose IV. CHU Lyon. 5j hospit.', 8450.00, 2160.00, 2160.00, 'clos', 'na', 0, 'low', 'Blanc Sophie'),
('SIN-SANTE-002', 'POL-SANTE-004', 'PRV-004', 'app-hc-002', 'sante', '2025-09-22', '2025-09-24', 'Lunettes progressives Essilor. Optic 2000 Aix.', 485.00, 292.90, 292.90, 'clos', 'na', 0, 'low', 'Blanc Sophie'),
('SIN-SANTE-003', 'POL-SANTE-009', 'PRV-009', 'app-hc-003', 'sante', '2025-10-28', '2025-11-05', 'Hospitalisation cardiaque — coronarographie + stent.', 8420.00, 2590.00, 2590.00, 'clos', 'na', 0, 'low', 'Roche Pierre'),
('SIN-SANTE-004', 'POL-SANTE-016', 'PRV-016', 'app-hc-004', 'sante', '2026-01-15', '2026-01-20', 'Maternité HFM Lyon + forfait naissance.', 3200.00, 940.00, 940.00, 'clos', 'na', 0, 'low', 'Blanc Sophie'),
('SIN-SANTE-005', 'POL-SANTE-006', 'PRV-006', 'app-hc-005', 'sante', '2026-03-05', '2026-03-07', 'Devis dentaire — couronne + bridge 3 éléments.', 2600.00, 645.00, NULL, 'en_cours', 'na', 0, 'low', 'Roche Pierre'),
('SIN-SANTE-006', 'POL-SANTE-026', 'PRV-026', 'app-hc-006', 'sante', '2025-11-15', '2025-11-17', 'Soins dentaires conservateurs. Dr. Bourgeois Grenoble.', 195.00, 64.50, 64.50, 'clos', 'na', 0, 'low', 'Blanc Sophie'),
('SIN-SANTE-007', 'POL-SANTE-024', 'PRV-024', 'app-hc-007', 'sante', '2026-01-08', '2026-01-10', 'Consultation cardiologie secteur 2. Paris 16e.', 120.00, 50.00, 50.00, 'clos', 'na', 0, 'low', 'Roche Pierre'),
('SIN-SANTE-008', 'POL-SANTE-012', 'PRV-012', 'app-hc-008', 'sante', '2026-03-28', '2026-03-30', 'IRM genou — en attente entente préalable.', 380.00, NULL, NULL, 'en_cours', 'na', 0, 'low', NULL),
-- Habitation (7)
('SIN-HAB-001', 'POL-HAB-013', 'PRV-013', 'app-house-hab-001', 'habitation', '2025-10-02', '2025-10-03', 'DDE — fuite canalisation cuisine. Expertise mandatée.', 5200.00, 4800.00, NULL, 'en_cours', 'assure', 100, 'low', 'Girard Luc'),
('SIN-HAB-002', 'POL-HAB-005', 'PRV-005', 'app-hab-002', 'habitation', '2025-04-18', '2025-04-20', 'DDE — fuite machine à laver. Parquet + plafond voisin.', 3200.00, 2950.00, 2950.00, 'clos', 'assure', 100, 'low', 'Girard Luc'),
('SIN-HAB-003', 'POL-HAB-015', 'PRV-015', 'app-hab-003', 'habitation', '2025-07-02', '2025-07-03', 'Cambriolage T2 Toulouse — fraude suspectée.', 12200.00, 0.00, 0.00, 'investigation', 'na', 0, 'high', 'Lefranc Pascal'),
('SIN-HAB-004', 'POL-HAB-020', 'PRV-020', 'app-hab-004', 'habitation', '2025-10-30', '2025-11-01', 'Inondation cave. Cat-nat en attente arrêté.', 7500.00, NULL, NULL, 'en_cours', 'na', 0, 'low', 'Girard Luc'),
('SIN-HAB-005', 'POL-HAB-028', 'PRV-028', 'app-hab-005', 'habitation', '2025-06-18', '2025-06-20', 'Grêle Colmar — tuiles + gouttière + velux.', 4100.00, 3800.00, 3800.00, 'clos', 'na', 0, 'low', 'Girard Luc'),
('SIN-HAB-006', 'POL-HAB-008', 'PRV-008', 'app-hab-006', 'habitation', '2026-02-05', '2026-02-06', 'Fissure mur porteur — travaux voisin.', NULL, NULL, NULL, 'en_cours', 'na', 0, 'medium', NULL),
('SIN-HAB-007', 'POL-HAB-030', 'PRV-030', 'app-hab-007', 'habitation', '2025-09-10', '2025-09-12', 'DDE locataire — fuite ballon voisin. Recours MACIF.', 1130.00, 1130.00, 1130.00, 'clos', 'tiers', 0, 'low', 'Girard Luc')
ON CONFLICT (sinistre_id) DO NOTHING;
"""

# ── Seed: Paiements ───────────────────────────────────────────────────────

SEED_PAIEMENTS = """
INSERT INTO workbenchiq.paiements (paiement_id, sinistre_id, client_id, montant, type_paiement, date_paiement, reference, statut) VALUES
('PAY-001', 'SIN-AUTO-001', 'PRV-007', 1900.00, 'indemnisation', '2024-12-20', 'VIR-2024-AUTO-0078', 'effectue'),
('PAY-002', 'SIN-AUTO-001', 'PRV-007', 1900.00, 'recours', '2025-02-15', 'REC-2025-MAIF-0012', 'effectue'),
('PAY-003', 'SIN-AUTO-003', 'PRV-003', 580.00, 'indemnisation', '2025-04-05', 'VIR-2025-AUTO-0034', 'effectue'),
('PAY-004', 'SIN-AUTO-004', 'PRV-010', 620.00, 'indemnisation', '2025-06-28', 'VIR-2025-AUTO-0056', 'effectue'),
('PAY-005', 'SIN-AUTO-006', 'PRV-018', 1350.00, 'indemnisation', '2025-09-10', 'VIR-2025-AUTO-0098', 'effectue'),
('PAY-006', 'SIN-AUTO-006', 'PRV-018', 1350.00, 'recours', '2025-11-20', 'REC-2025-TIERS-0045', 'effectue'),
('PAY-007', 'SIN-SANTE-001', 'PRV-017', 2160.00, 'indemnisation', '2025-03-25', 'VIR-2025-SAN-0017', 'effectue'),
('PAY-008', 'SIN-SANTE-002', 'PRV-004', 292.90, 'indemnisation', '2025-10-10', 'VIR-2025-SAN-0004', 'effectue'),
('PAY-009', 'SIN-SANTE-003', 'PRV-009', 2590.00, 'indemnisation', '2025-12-01', 'VIR-2025-SAN-0009', 'effectue'),
('PAY-010', 'SIN-SANTE-004', 'PRV-016', 940.00, 'indemnisation', '2026-02-15', 'VIR-2026-SAN-0016', 'effectue'),
('PAY-011', 'SIN-SANTE-006', 'PRV-026', 64.50, 'indemnisation', '2025-12-05', 'VIR-2025-SAN-0026', 'effectue'),
('PAY-012', 'SIN-SANTE-007', 'PRV-024', 50.00, 'indemnisation', '2026-02-01', 'VIR-2026-SAN-0024', 'effectue'),
('PAY-013', 'SIN-HAB-002', 'PRV-005', 2950.00, 'indemnisation', '2025-06-15', 'VIR-2025-HAB-0005', 'effectue'),
('PAY-014', 'SIN-HAB-005', 'PRV-028', 3800.00, 'indemnisation', '2025-08-10', 'VIR-2025-HAB-0028', 'effectue'),
('PAY-015', 'SIN-HAB-007', 'PRV-030', 1130.00, 'indemnisation', '2025-11-01', 'VIR-2025-HAB-0030', 'effectue'),
('PAY-016', 'SIN-HAB-007', 'PRV-030', 1130.00, 'recours', '2026-01-15', 'REC-2026-MACIF-0030', 'en_attente')
ON CONFLICT (paiement_id) DO NOTHING;
"""

# ── Seed: Prêts ───────────────────────────────────────────────────────────

SEED_PRETS = """
INSERT INTO workbenchiq.prets (pret_id, client_id, application_id, type_pret, montant_pret, valeur_bien, ltv, taux_interet, duree_mois, mensualite, ratio_gds, ratio_tds, score_credit, statut, date_demande, date_decision) VALUES
('PRET-SC', 'PRV-SC', 'app-sc-mtg-001', 'conventionnel', 520000.00, 650000.00, 80.00, 3.490, 300, 2580.00, 28.00, 35.00, 780, 'approuve', '2021-09-10', '2021-10-05'),
('PRET-MW', 'PRV-MW', 'app-mw-mtg-001', 'conventionnel', 480000.00, 620000.00, 77.42, 3.790, 300, 2480.00, 32.00, 38.00, 720, 'approuve', '2021-04-15', '2021-05-10'),
('PRET-PP', 'PRV-PP', 'app-pp-mtg-001', 'conventionnel', 400000.00, 550000.00, 72.73, 3.290, 300, 1950.00, 25.00, 31.00, 760, 'approuve', '2022-01-05', '2022-02-01'),
('PRET-002', 'PRV-002', 'app-mtg-004', 'conventionnel', 450000.00, 540000.00, 83.33, 3.150, 300, 2250.00, 27.00, 27.00, 750, 'approuve', '2025-07-15', '2025-08-10'),
('PRET-029', 'PRV-029', 'app-mtg-005', 'ptz', 220000.00, 310000.00, 70.97, 0.000, 300, 733.00, 22.00, 28.00, 700, 'en_cours', '2026-02-10', NULL),
('PRET-014', 'PRV-014', 'app-mtg-006', 'rachat', 180000.00, 290000.00, 62.07, 3.100, 240, 920.00, 22.00, 22.00, 790, 'approuve', '2025-05-12', '2025-06-05'),
('PRET-019', 'PRV-019', 'app-mtg-007', 'conventionnel', 380000.00, 460000.00, 82.61, 3.650, 300, 2100.00, 29.00, 29.00, 740, 'en_cours', '2026-01-28', NULL),
('PRET-035', 'PRV-035', 'app-mtg-008', 'conventionnel', 0.00, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'error', '2026-03-10', NULL)
ON CONFLICT (pret_id) DO NOTHING;
"""

# ── Indexes ───────────────────────────────────────────────────────────────

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_sinistres_type ON workbenchiq.sinistres(type_sinistre);",
    "CREATE INDEX IF NOT EXISTS idx_sinistres_statut ON workbenchiq.sinistres(statut);",
    "CREATE INDEX IF NOT EXISTS idx_sinistres_date ON workbenchiq.sinistres(date_sinistre);",
    "CREATE INDEX IF NOT EXISTS idx_sinistres_client ON workbenchiq.sinistres(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_polices_type ON workbenchiq.polices(type_police);",
    "CREATE INDEX IF NOT EXISTS idx_polices_client ON workbenchiq.polices(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_paiements_sinistre ON workbenchiq.paiements(sinistre_id);",
    "CREATE INDEX IF NOT EXISTS idx_prets_client ON workbenchiq.prets(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_prets_statut ON workbenchiq.prets(statut);",
]


async def main() -> None:
    s = load_settings()
    await init_pool(s.database)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS workbenchiq")

        for label, sql in [
            ("clients", CLIENTS_SQL),
            ("polices", POLICES_SQL),
            ("sinistres", SINISTRES_SQL),
            ("paiements", PAIEMENTS_SQL),
            ("prets", PRETS_SQL),
        ]:
            await conn.execute(sql)
            print(f"  Created: workbenchiq.{label}")

        for label, sql in [
            ("clients", SEED_CLIENTS),
            ("polices", SEED_POLICES),
            ("sinistres", SEED_SINISTRES),
            ("paiements", SEED_PAIEMENTS),
            ("prets", SEED_PRETS),
        ]:
            await conn.execute(sql)
            count = await conn.fetchval(f"SELECT COUNT(*) FROM workbenchiq.{label}")
            print(f"  Seeded: workbenchiq.{label} = {count} rows")

        for idx_sql in INDEXES_SQL:
            await conn.execute(idx_sql)
        print(f"  Created {len(INDEXES_SQL)} indexes")

        # ── Summary ───────────────────────────────────────────────────
        print("\n=== Business Data Summary ===")
        for tbl in ["clients", "polices", "sinistres", "paiements", "prets"]:
            c = await conn.fetchval(f"SELECT COUNT(*) FROM workbenchiq.{tbl}")
            print(f"  workbenchiq.{tbl}: {c} rows")

        types = await conn.fetch(
            "SELECT type_sinistre, COUNT(*) n, COALESCE(SUM(montant_reclame),0) total "
            "FROM workbenchiq.sinistres GROUP BY type_sinistre ORDER BY type_sinistre"
        )
        print("\n=== Sinistres par type ===")
        for r in types:
            print(f"  {r['type_sinistre']}: {r['n']} sinistres, {r['total']} EUR")

        prets = await conn.fetch(
            "SELECT statut, COUNT(*) n, COALESCE(SUM(montant_pret),0) total "
            "FROM workbenchiq.prets GROUP BY statut"
        )
        print("\n=== Prets par statut ===")
        for r in prets:
            print(f"  {r['statut']}: {r['n']} prets, {r['total']} EUR")


if __name__ == "__main__":
    asyncio.run(main())
