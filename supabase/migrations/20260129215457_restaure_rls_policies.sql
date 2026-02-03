-- =============================================================================
-- 1. REPARACIÓN DE PERMISOS BÁSICOS (GRANTS)
-- =============================================================================
-- Permite al usuario autenticado "ver" estas tablas. Sin esto, RLS ni siquiera arranca.
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT ON TABLE public.profiles TO authenticated;
GRANT SELECT ON TABLE public.organizations TO authenticated;
GRANT SELECT ON TABLE public.organization_members TO authenticated;

-- =============================================================================
-- 2. FUNCIÓN DE SEGURIDAD (La llave maestra)
-- =============================================================================
-- Aseguramos que la función que chequea si eres admin exista y sea segura.
CREATE OR REPLACE FUNCTION public.is_admin_secure()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER -- Corre como superusuario para saltarse bloqueos
SET search_path = public
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND is_platform_admin = TRUE
    );
END;
$$;

-- =============================================================================
-- 3. POLÍTICAS PARA: ORGANIZATION_MEMBERS
-- =============================================================================
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;

-- Borrar políticas viejas que puedan tener nombres raros
DROP POLICY IF EXISTS "members_read_own" ON public.organization_members;
DROP POLICY IF EXISTS "members_read_admin" ON public.organization_members;
DROP POLICY IF EXISTS "read_members" ON public.organization_members;

-- Política A: "Puedo ver mis propias membresías"
CREATE POLICY "members_read_own" ON public.organization_members
FOR SELECT USING (
    user_id = auth.uid()
);

-- Política B: "Si soy Platform Admin, veo todo"
CREATE POLICY "members_read_admin" ON public.organization_members
FOR SELECT USING (
    public.is_admin_secure() = TRUE
);

-- =============================================================================
-- 4. POLÍTICAS PARA: ORGANIZATIONS
-- =============================================================================
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "orgs_read_member" ON public.organizations;
DROP POLICY IF EXISTS "orgs_read_admin" ON public.organizations;
DROP POLICY IF EXISTS "read_organizations" ON public.organizations;

-- Política A: "Puedo ver las organizaciones de las que soy miembro"
CREATE POLICY "orgs_read_member" ON public.organizations
FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE organization_id = id
        AND user_id = auth.uid()
    )
);

-- Política B: "Si soy Platform Admin, veo todas"
CREATE POLICY "orgs_read_admin" ON public.organizations
FOR SELECT USING (
    public.is_admin_secure() = TRUE
);

-- =============================================================================
-- 5. RE-ASEGURAR PROFILES (Por si acaso)
-- =============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "profiles_read_policy" ON public.profiles;

CREATE POLICY "profiles_read_policy" ON public.profiles
FOR SELECT USING (
    auth.uid() = id 
    OR public.is_admin_secure() = TRUE
);

-- Confirmación final
SELECT '✅ Sistema de Permisos Reparado Completo (Perfiles + Orgs + Miembros)' as status;