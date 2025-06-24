# Problème : Switch d'organisation intempestif lors de la navigation dans les workflows

## 🔍 Analyse du problème

### Symptômes observés
- L'organisation change automatiquement quand on navigue dans un workflow
- Ce changement se produit sans que l'utilisateur clique explicitement sur un sélecteur d'organisation
- Le comportement est "intempestif" car non désiré par l'utilisateur

### 🔎 Cause identifiée

Le problème provient de l'architecture actuelle du back-end qui expose systématiquement l'`organization_id` dans les réponses API :

#### 1. Structure des URLs
```
/projects/{project_id}/graph/{graph_runner_id}
```

#### 2. Résolution automatique d'organisation
Quand on accède à un projet via son ID, le système :

```python
# ada_backend/routers/auth_router.py:90-98
project = get_project(session, project_id)
access = await get_user_access_to_organization(
    user=user,
    organization_id=project.organization_id,  # ← Organisation récupérée automatiquement
)
```

#### 3. Exposition dans les réponses API
```python
# ada_backend/schemas/project_schema.py:21-24
class ProjectResponse(ProjectSchema):
    organization_id: UUID  # ← Toujours exposé
    created_at: str
    updated_at: str
```

#### 4. Routes concernées
- `GET /projects/{project_id}` 
- `GET /projects/{project_id}/graph/{graph_runner_id}`
- `PUT /projects/{project_id}/graph/{graph_runner_id}`
- `POST /projects/{project_id}/graph/{graph_runner_id}/deploy`

## 💡 Solutions proposées

### Solution 1: Contexte d'organisation explicite (Recommandée)

**Principe :** Ne plus changer automatiquement l'organisation côté front-end, même si l'API retourne l'`organization_id`.

#### Modifications côté front-end :
1. **État d'organisation séparé** : Séparer l'organisation "courante" de l'organisation du projet en cours
2. **Changement explicite uniquement** : L'organisation ne change que lors d'un clic explicite sur un sélecteur
3. **Affichage contextuel** : Afficher l'organisation du projet comme information, pas comme changement d'état

#### Avantages :
- ✅ Résout complètement le problème
- ✅ Aucune modification back-end nécessaire
- ✅ Maintient la cohérence des données
- ✅ UX plus prévisible

### Solution 2: API optionnelle d'organisation

**Principe :** Modifier le back-end pour rendre l'exposition de l'`organization_id` optionnelle.

#### Modifications à implémenter :

```python
# Nouveau schéma de réponse optionnel
class ProjectResponseMinimal(BaseModel):
    project_id: UUID
    project_name: str
    description: Optional[str] = None
    companion_image_url: Optional[str] = None
    created_at: str
    updated_at: str
    # organization_id: UUID  ← Retiré

# Paramètre optionnel dans les endpoints
@router.get("/{project_id}")
def get_project_endpoint(
    project_id: UUID,
    include_org: bool = Query(False, description="Include organization_id in response"),
    # ...
):
    # Logique conditionnelle
```

#### Avantages :
- ✅ Contrôle granulaire
- ✅ Rétrocompatibilité

#### Inconvénients :
- ❌ Modifications back-end importantes
- ❌ Complexité ajoutée

### Solution 3: Header de contexte

**Principe :** Utiliser un header HTTP pour indiquer quand ne pas exposer l'organisation.

```python
@router.get("/{project_id}")
def get_project_endpoint(
    project_id: UUID,
    x_navigation_context: Optional[str] = Header(None),
    # ...
):
    response = get_project_service(session, project_id)
    
    # Si c'est une navigation workflow, ne pas exposer org_id
    if x_navigation_context == "workflow-navigation":
        response.organization_id = None
    
    return response
```

## 🎯 Recommandation

**Solution 1** est recommandée car elle :
- Résout le problème à la source (front-end)
- Ne nécessite aucune modification back-end
- Améliore l'UX en rendant le comportement plus prévisible
- Respecte le principe de séparation des responsabilités

## 🛠️ Implémentation suggérée (Front-end)

```typescript
// État séparé pour l'organisation
interface AppState {
  selectedOrganization: Organization;  // Organisation choisie par l'utilisateur
  currentProjectOrganization?: Organization;  // Organisation du projet courant (info seulement)
  // ...
}

// Fonction pour changer d'organisation (uniquement sur clic explicite)
const switchOrganization = (org: Organization) => {
  setSelectedOrganization(org);
};

// Ne PAS changer automatiquement l'organisation lors du changement de projet
const navigateToProject = (projectId: string) => {
  // Navigation sans changement d'organisation
  // L'organisation du projet est affichée comme info contextuelle
};
```

## 📝 Prochaines étapes

1. **Validation avec l'équipe front-end** : Confirmer que cette approche est compatible avec l'architecture actuelle
2. **Implémentation côté front-end** : Séparer l'état d'organisation sélectionnée de l'organisation du projet
3. **Tests** : Vérifier que la navigation dans les workflows ne change plus l'organisation
4. **Documentation** : Mettre à jour la documentation UX pour clarifier ce comportement