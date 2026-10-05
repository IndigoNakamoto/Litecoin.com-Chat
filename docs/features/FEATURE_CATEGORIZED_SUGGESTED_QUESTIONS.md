# Categorized Suggested Questions Feature

## Overview

This feature adds **category-based organization** to suggested questions, allowing users to first select a category and then view questions specific to that category. This improves discoverability and helps users find relevant questions more easily by organizing them into logical groups.

**Status**: ✅ **Implemented** (2026-10-05) — single optional `category` relationship on `suggested-questions`; the chat UI loads `GET /api/v1/suggested-questions` (categories + questions + `cached` flags) and renders `landing/TopicPicker.tsx` → `landing/QuestionGrid.tsx`, falling back to the flat grid when no category has questions. Sub-categories roll up to their top-level parent. Clicking a question sends `category_hint` with the chat request. Production was seeded on 2026-10-05 with six top-level categories (Litecoin Basics, Privacy & MWEB, Fees/Payments & Everyday Use, Mining & Network Security, Live Network Data, Ecosystem & Foundation) and 39 questions, each screened live against the backend before activation; live-data questions are intentionally not pre-cached (`is_precacheable_answer` in `backend/main.py`). The sections below are the original design; where they differ, the code is the reference.

**Priority**: Medium - Enhances user experience and content organization

**Last Updated**: 2026-10-05

---

## Table of Contents

1. [Feature Summary](#feature-summary)
2. [Business Requirements](#business-requirements)
3. [Technical Requirements](#technical-requirements)
4. [User Experience Flow](#user-experience-flow)
5. [Implementation Details](#implementation-details)
6. [Data Model Changes](#data-model-changes)
7. [Frontend Implementation](#frontend-implementation)
8. [Backend/Payload CMS Changes](#backendpayload-cms-changes)
9. [Migration Strategy](#migration-strategy)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Future Enhancements](#future-enhancements)

---

## Feature Summary

### Problem Statement

Currently, suggested questions are displayed as a flat list:
- All questions are shown together without organization
- Users must scroll through many questions to find relevant ones
- No way to filter or organize questions by topic
- Difficult to discover questions in specific areas of interest
- Questions may cover diverse topics (technical, trading, getting started, etc.) but are all mixed together

### Solution

Implement a **two-step selection process**:
1. **Category Selection**: Users first see available categories (using the same categories as Articles)
2. **Question Display**: After selecting a category, users see questions filtered to that category
3. **"All Topics" Option**: Users can still view all questions without category filtering

### Key Benefits

- ✅ **Better Organization**: Questions grouped by topic/category
- ✅ **Improved Discoverability**: Users can find relevant questions faster
- ✅ **Consistent with Articles**: Uses the same category system as the knowledge base articles
- ✅ **Flexible Navigation**: Users can switch between categories or view all
- ✅ **Backward Compatible**: Questions without categories still appear in "All Topics"
- ✅ **Admin-Friendly**: Easy to manage categories and assign questions via Payload CMS

---

## Business Requirements

### BR-1: Category-Based Question Organization
- **Requirement**: Questions should be organized by categories
- **Priority**: Critical
- **Acceptance Criteria**:
  - Questions can be assigned to one or more categories
  - Categories are the same as those used for Articles
  - Users can select a category to filter questions
  - "All Topics" option shows all questions regardless of category
  - Questions without categories appear in "All Topics" view

### BR-2: Category Selection UI
- **Requirement**: Users should see categories before questions
- **Priority**: Critical
- **Acceptance Criteria**:
  - Category selection screen appears first (if categories exist)
  - Categories display with icons and names
  - "All Topics" option is prominently displayed
  - Smooth navigation between category selection and question display
  - Back button to return to category selection

### BR-3: Category Filtering
- **Requirement**: Questions should be filtered by selected category
- **Priority**: Critical
- **Acceptance Criteria**:
  - Only questions in selected category are displayed
  - Filtering happens on the frontend (via API query)
  - "I'm Feeling Lit" button respects category selection (randomizes within category)
  - Empty state shown if no questions in selected category

### BR-4: Backward Compatibility
- **Requirement**: Existing questions without categories should still work
- **Priority**: High
- **Acceptance Criteria**:
  - Questions without categories appear in "All Topics" view
  - System gracefully handles questions with no category assignment
  - No breaking changes to existing question data
  - Migration path for assigning categories to existing questions

### BR-5: Admin Management
- **Requirement**: Admins should be able to assign categories to questions in Payload CMS
- **Priority**: High
- **Acceptance Criteria**:
  - Category field visible in Payload CMS admin interface
  - Category selection uses same UI component as Articles (CategorySelector)
  - Support for single or multiple categories per question
  - Easy to bulk-assign categories to questions

---

## Technical Requirements

### TR-1: Category Relationship Field
- **Requirement**: Add category relationship to SuggestedQuestions collection
- **Priority**: Critical
- **Details**:
  - Field type: `relationship` to `categories` collection
  - Support single category (recommended) or multiple categories (`hasMany: true`)
  - Optional field (for backward compatibility)
  - Use same CategorySelector component as Articles

### TR-2: Category API Integration
- **Requirement**: Frontend should fetch categories from Payload CMS
- **Priority**: Critical
- **Details**:
  - Fetch categories on component mount
  - Filter to show only main categories (no parent) in selector
  - Support hierarchical categories (parent-child relationships)
  - Handle API errors gracefully

### TR-3: Question Filtering
- **Requirement**: Filter questions by category in API query
- **Priority**: Critical
- **Details**:
  - Add category filter to Payload CMS API query
  - Support filtering by category ID
  - Handle null/undefined category (show all)
  - Maintain existing query parameters (isActive, sort, limit)

### TR-4: Frontend State Management
- **Requirement**: Manage category selection and question filtering in React
- **Priority**: High
- **Details**:
  - State for selected category (null = "All")
  - State for categories list
  - State for filtered questions
  - Reset pagination when category changes

### TR-5: UI/UX Enhancements
- **Requirement**: Smooth transitions and navigation
- **Priority**: Medium
- **Details**:
  - Animated category selection screen
  - Back button to return to categories
  - Loading states during category/question fetching
  - Empty states for no categories or no questions

---

## User Experience Flow

### Flow Diagram

```
User lands on chat page
    │
    ▼
┌─────────────────────────────┐
│ Category Selection Screen   │  ← NEW (if categories exist)
│ - "All Topics" button       │
│ - Category cards with icons │
│ - Click to select category  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Questions Display Screen     │  ← EXISTING (filtered by category)
│ - Questions for category    │
│ - "Show me more" pagination │
│ - "I'm Feeling Lit" button   │
│ - Back to categories button  │
└─────────────────────────────┘
```

### Detailed User Flow

1. **Initial Load**:
   - User opens chat interface
   - Component fetches categories from Payload CMS
   - If categories exist: Show category selection screen
   - If no categories: Show all questions directly (backward compatible)

2. **Category Selection**:
   - User sees grid of category cards
   - Each card shows: icon, category name
   - "All Topics" card is prominently displayed
   - User clicks a category card

3. **Question Display**:
   - Component fetches questions filtered by selected category
   - Questions displayed in grid (existing UI)
   - "Back to categories" button visible
   - "I'm Feeling Lit" randomizes within selected category

4. **Navigation**:
   - User can click "Back to categories" to return to category selection
   - User can select different category to see different questions
   - Pagination resets when category changes

5. **Edge Cases**:
   - No categories: Show all questions directly (no category screen)
   - No questions in category: Show empty state with back button
   - Category API fails: Fall back to showing all questions

---

## Implementation Details

### File Structure

```
payload_cms/
└── src/
    └── collections/
        └── SuggestedQuestions.ts  # MODIFIED - Add category field

frontend/
└── src/
    └── components/
        └── SuggestedQuestions.tsx  # MODIFIED - Add category selection
```

### Component State Structure

```typescript
interface SuggestedQuestionsState {
  // Categories
  categories: Category[];
  isLoadingCategories: boolean;
  selectedCategory: string | null; // null = "All Topics"
  
  // Questions
  questions: SuggestedQuestion[];
  allQuestions: SuggestedQuestion[];
  currentPage: number;
  isLoading: boolean;
  error: string | null;
}
```

### API Query Examples

**Fetch Categories**:
```
GET /api/categories?sort=order&limit=100&depth=1
```

**Fetch Questions (All)**:
```
GET /api/suggested-questions?where[isActive][equals]=true&sort=order&limit=100&depth=1
```

**Fetch Questions (Filtered by Category)**:
```
GET /api/suggested-questions?where[isActive][equals]=true&where[category][equals]={categoryId}&sort=order&limit=100&depth=1
```

---

## Data Model Changes

### Payload CMS Collection Update

**File**: `payload_cms/src/collections/SuggestedQuestions.ts`

**Changes**:
- Add `category` relationship field
- Update `defaultColumns` to include category
- Make category optional for backward compatibility

**Field Definition**:

```typescript
{
  name: 'category',
  type: 'relationship',
  relationTo: 'categories',
  required: false, // Optional for backward compatibility
  // hasMany: true, // Uncomment if you want multiple categories per question
  admin: {
    description: 'Category this question belongs to (optional - questions without category will show in "All" view)',
    components: {
      Field: CategorySelector as any, // Use same component as Articles
    },
  },
}
```

**Option 1: Single Category (Recommended)**
- Each question belongs to one category
- Simpler UI and filtering logic
- Easier to manage

**Option 2: Multiple Categories**
- Each question can belong to multiple categories
- More flexible but more complex
- Requires `hasMany: true`
- Frontend filtering logic needs to check if question's categories array includes selected category

---

## Frontend Implementation

### Component Updates

**File**: `frontend/src/components/SuggestedQuestions.tsx`

**Key Changes**:

1. **Add Category State**:
   ```typescript
   const [categories, setCategories] = useState<Category[]>([]);
   const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
   const [isLoadingCategories, setIsLoadingCategories] = useState(true);
   ```

2. **Fetch Categories on Mount**:
   ```typescript
   useEffect(() => {
     const fetchCategories = async () => {
       // Fetch from Payload CMS
       // Filter to main categories (no parent)
       // Set categories state
     };
     fetchCategories();
   }, []);
   ```

3. **Filter Questions by Category**:
   ```typescript
   useEffect(() => {
     const fetchQuestions = async () => {
       const whereClause: any = {
         isActive: { equals: true }
       };
       
       if (selectedCategory !== null) {
         whereClause.category = { equals: selectedCategory };
       }
       
       // Fetch with category filter
     };
     fetchQuestions();
   }, [selectedCategory]);
   ```

4. **Category Selection Screen**:
   - Show if `categories.length > 0 && selectedCategory === null`
   - Display category cards in grid
   - Include "All Topics" option
   - Animate with Framer Motion

5. **Question Display Screen**:
   - Show filtered questions
   - Display selected category name in header
   - "Back to categories" button
   - "I'm Feeling Lit" respects category selection

### UI Components

**Category Selection Screen**:
- Grid layout (2 columns mobile, 3-4 columns desktop)
- Category cards with:
  - Icon (emoji or custom icon)
  - Category name
  - Hover effects
- "All Topics" card prominently displayed

**Question Display Screen**:
- Existing question grid (unchanged)
- Header shows category name or "All Topics"
- Back button to return to categories
- "I'm Feeling Lit" button (category-aware)

---

## Backend/Payload CMS Changes

### Collection Schema Update

**File**: `payload_cms/src/collections/SuggestedQuestions.ts`

**Complete Field List**:

```typescript
fields: [
  {
    name: 'question',
    type: 'text',
    required: true,
  },
  {
    name: 'category',  // NEW
    type: 'relationship',
    relationTo: 'categories',
    required: false,
    admin: {
      description: 'Category this question belongs to',
      components: {
        Field: CategorySelector as any,
      },
    },
  },
  {
    name: 'order',
    type: 'number',
    required: true,
    defaultValue: 0,
  },
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: true,
  },
]
```

### Admin Interface

- Category field appears in SuggestedQuestions admin panel
- Uses same CategorySelector component as Articles
- Supports hierarchical category selection
- Easy to assign categories to questions

---

## Migration Strategy

### Phase 1: Add Category Field (Non-Breaking)
- Add category field to SuggestedQuestions collection
- Field is optional, so existing questions remain valid
- No data migration required immediately

### Phase 2: Assign Categories to Existing Questions
- Admins manually assign categories to existing questions via Payload CMS
- Can be done incrementally
- Questions without categories still appear in "All Topics"

### Phase 3: Frontend Implementation
- Deploy frontend changes
- System gracefully handles questions without categories
- Category selection only shows if categories exist

### Migration Checklist

- [ ] Update SuggestedQuestions collection schema
- [ ] Deploy Payload CMS changes
- [ ] Assign categories to existing questions (manual or script)
- [ ] Update frontend component
- [ ] Test category selection flow
- [ ] Test backward compatibility (no categories)
- [ ] Test filtering by category
- [ ] Test "All Topics" view
- [ ] Test "I'm Feeling Lit" with category selection

### Bulk Category Assignment Script (Optional)

If you have many questions to categorize, you could create a script:

```python
# Example: Assign categories based on question keywords
# This is just an example - customize based on your needs

def assign_categories_to_questions():
    questions = fetch_all_questions()
    categories = fetch_all_categories()
    
    for question in questions:
        # Determine category based on question text
        category = determine_category(question.text, categories)
        if category:
            update_question_category(question.id, category.id)
```

---

## Configuration

### Environment Variables

No new environment variables required. Uses existing:
- `NEXT_PUBLIC_PAYLOAD_URL` - Payload CMS URL (frontend)
- `PAYLOAD_PUBLIC_SERVER_URL` - Payload CMS URL (backend)

### Payload CMS Configuration

No additional configuration needed. Uses existing:
- Categories collection (already exists)
- CategorySelector component (already exists)

---

## Testing

### Unit Tests

**Frontend Component**:
- Test category fetching
- Test category selection
- Test question filtering by category
- Test "All Topics" option
- Test backward compatibility (no categories)
- Test empty states

**Payload CMS**:
- Test category field in admin interface
- Test category assignment
- Test API filtering by category

### Integration Tests

**End-to-End Flow**:
1. User opens chat → sees category selection
2. User selects category → sees filtered questions
3. User clicks "Back to categories" → returns to selection
4. User selects "All Topics" → sees all questions
5. User clicks "I'm Feeling Lit" → randomizes within category

**Edge Cases**:
- No categories exist → shows all questions directly
- No questions in selected category → shows empty state
- Category API fails → falls back to all questions
- Question without category → appears in "All Topics"

### Manual Testing Checklist

- [ ] Category selection screen displays correctly
- [ ] Categories load from Payload CMS
- [ ] Clicking category filters questions correctly
- [ ] "All Topics" shows all questions
- [ ] Back button returns to category selection
- [ ] "I'm Feeling Lit" respects category selection
- [ ] Questions without categories appear in "All Topics"
- [ ] Empty state shows when no questions in category
- [ ] Mobile responsive design works
- [ ] Animations are smooth

---

## Future Enhancements

### Phase 2: Subcategory Support
- Show subcategories in category selection
- Allow filtering by subcategory
- Hierarchical category navigation

### Phase 3: Category Icons and Descriptions
- Display category descriptions in selection screen
- Custom icons per category
- Category-specific styling

### Phase 4: Smart Category Suggestions
- Suggest categories based on user's previous questions
- Highlight popular categories
- Show question count per category

### Phase 5: Category Analytics
- Track which categories are most popular
- Monitor category selection patterns
- A/B testing for category organization

### Phase 6: Multi-Category Support
- Allow questions to belong to multiple categories
- Show questions in all relevant categories
- Improved filtering logic

---

## Related Documentation

- [Suggested Questions Caching Feature](./FEATURE_SUGGESTED_QUESTION_CACHING.md)
- [Payload CMS Integration](../milestones/milestone_5_payload_cms_setup_integration.md)
- [Category Collection](../payload_cms/src/collections/Category.ts)
- [Article Collection](../payload_cms/src/collections/Article.ts) - Reference for category field implementation

---

## Changelog

### 2025-01-XX - Feature Document Created
- Documented categorized suggested questions feature
- Defined requirements and implementation approach
- Outlined migration strategy

---

## Implementation Notes

### Design Decisions

1. **Single vs Multiple Categories**: Recommended single category for simplicity, but can be changed to multiple if needed
2. **Category Selection First**: Users select category before seeing questions (better UX)
3. **Backward Compatibility**: Questions without categories still work (appear in "All Topics")
4. **Same Categories as Articles**: Reuses existing category system for consistency

### Key Considerations

- **Performance**: Category filtering happens via API query (efficient)
- **Scalability**: Works with any number of categories and questions
- **Maintainability**: Uses existing CategorySelector component (DRY principle)
- **User Experience**: Smooth transitions and clear navigation

---

**Document Status**: 📋 Planned - Ready for Implementation

