-- Migration: CRM Organization Profiles
-- Date: 2026-02-25
-- Creates crm.organization_profiles to enrich public.organizations with CRM-specific data,
-- following the same pattern as crm.contacts enriching auth.users.
-- Also seeds org_industry and org_company_size into crm.field_options so they are
-- configurable from the admin panel (same as gender/education_level/occupation for contacts).

-- 1. Create crm.organization_profiles
CREATE TABLE IF NOT EXISTS crm.organization_profiles (
    org_id       UUID PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
    website      TEXT,
    phone        TEXT,
    industry     TEXT,
    company_size TEXT,
    address      TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER update_crm_org_profiles_modtime
    BEFORE UPDATE ON crm.organization_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE crm.organization_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Platform Admins manage all org profiles" ON crm.organization_profiles
    FOR ALL USING (crm.is_platform_admin());

CREATE POLICY "Org Members read their org profile" ON crm.organization_profiles
    FOR SELECT USING (crm.is_org_member(org_id));

CREATE POLICY "Org Admins write their org profile" ON crm.organization_profiles
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.organization_members
            WHERE user_id = auth.uid()
              AND organization_id = org_id
              AND status = 'active'
              AND role IN ('owner', 'admin')
        )
    );

-- 2. Seed org_industry into crm.field_options
INSERT INTO crm.field_options (field_name, value, label, sort_order) VALUES
  -- Energía
  ('org_industry', 'energia',              'Energía',                              1),
  ('org_industry', 'petroleo_gas',         'Petróleo y Gas',                       2),
  ('org_industry', 'energia_renovable',    'Energía Renovable',                    3),
  -- Materiales
  ('org_industry', 'materiales',           'Materiales',                           4),
  ('org_industry', 'quimica',              'Química',                              5),
  ('org_industry', 'mineria',              'Minería',                              6),
  -- Industriales
  ('org_industry', 'industriales',         'Industriales',                         7),
  ('org_industry', 'manufactura',          'Manufactura',                          8),
  ('org_industry', 'construccion',         'Construcción',                         9),
  ('org_industry', 'logistica',            'Logística y Transporte',              10),
  ('org_industry', 'aeroespacial',         'Aeroespacial y Defensa',              11),
  -- Consumo Discrecional
  ('org_industry', 'consumo_discrecional', 'Consumo Discrecional',                12),
  ('org_industry', 'retail',               'Retail / Comercio',                   13),
  ('org_industry', 'automoviles',          'Automóviles',                         14),
  ('org_industry', 'turismo_hospitalidad', 'Turismo y Hospitalidad',              15),
  ('org_industry', 'entretenimiento',      'Entretenimiento y Medios',            16),
  -- Consumo Básico
  ('org_industry', 'consumo_basico',       'Consumo Básico',                      17),
  ('org_industry', 'alimentos_bebidas',    'Alimentos y Bebidas',                 18),
  ('org_industry', 'salud_personal',       'Salud Personal y Hogar',              19),
  -- Salud
  ('org_industry', 'salud',                'Salud',                               20),
  ('org_industry', 'farmaceutica',         'Farmacéutica y Biotecnología',        21),
  ('org_industry', 'dispositivos_medicos', 'Dispositivos Médicos',                22),
  ('org_industry', 'servicios_salud',      'Servicios de Salud',                  23),
  -- Financiero
  ('org_industry', 'financiero',           'Financiero',                          24),
  ('org_industry', 'banca',                'Banca',                               25),
  ('org_industry', 'seguros',              'Seguros',                             26),
  ('org_industry', 'fintech',              'Fintech',                             27),
  ('org_industry', 'gestion_activos',      'Gestión de Activos',                  28),
  -- Tecnología
  ('org_industry', 'tecnologia',           'Tecnología de la Información',        29),
  ('org_industry', 'software',             'Software y SaaS',                     30),
  ('org_industry', 'hardware',             'Hardware y Semiconductores',          31),
  ('org_industry', 'servicios_ti',         'Servicios de TI y Consultoría',       32),
  ('org_industry', 'ciberseguridad',       'Ciberseguridad',                      33),
  ('org_industry', 'inteligencia_artificial', 'Inteligencia Artificial',          34),
  -- Comunicaciones
  ('org_industry', 'comunicaciones',       'Servicios de Comunicación',           35),
  ('org_industry', 'telecomunicaciones',   'Telecomunicaciones',                  36),
  ('org_industry', 'medios_digitales',     'Medios Digitales y Redes Sociales',   37),
  -- Servicios Públicos
  ('org_industry', 'servicios_publicos',   'Servicios Públicos',                  38),
  ('org_industry', 'gobierno',             'Gobierno y Sector Público',           39),
  ('org_industry', 'ong',                  'ONG / Organizaciones Sin Fines de Lucro', 40),
  -- Inmobiliario
  ('org_industry', 'inmobiliario',         'Inmobiliario',                        41),
  -- Educación y otros
  ('org_industry', 'educacion',            'Educación',                           42),
  ('org_industry', 'edtech',               'EdTech',                              43),
  ('org_industry', 'recursos_humanos',     'Recursos Humanos y Capacitación',     44),
  ('org_industry', 'consultoria',          'Consultoría y Servicios Profesionales', 45),
  ('org_industry', 'legal',                'Legal y Compliance',                  46),
  ('org_industry', 'otro',                 'Otro',                                47)
ON CONFLICT (field_name, value) DO NOTHING;

-- 3. Seed org_company_size into crm.field_options
INSERT INTO crm.field_options (field_name, value, label, sort_order) VALUES
  ('org_company_size', '1-10',   '1–10 personas',   1),
  ('org_company_size', '11-50',  '11–50 personas',  2),
  ('org_company_size', '51-200', '51–200 personas', 3),
  ('org_company_size', '201-500','201–500 personas', 4),
  ('org_company_size', '500+',   '500+ personas',   5)
ON CONFLICT (field_name, value) DO NOTHING;
