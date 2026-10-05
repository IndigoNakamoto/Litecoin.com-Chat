import type { CollectionConfig } from 'payload'
import { isAdmin, isAdminOrPublisher } from '../access/isAdmin'

export const SuggestedQuestions: CollectionConfig = {
  slug: 'suggested-questions',
  admin: {
    useAsTitle: 'question',
    defaultColumns: ['question', 'category', 'order', 'isActive', 'updatedAt'],
    group: 'Content Management',
    description:
      'Manage suggested questions displayed to users on the chat interface. ' +
      'Assign a category so the question appears under that topic on the landing page; ' +
      'uncategorised questions only appear under "All topics".',
  },
  access: {
    read: () => true, // Public read access for frontend
    create: isAdminOrPublisher,
    update: isAdminOrPublisher,
    delete: isAdmin,
  },
  fields: [
    {
      name: 'question',
      type: 'text',
      required: true,
      admin: {
        description: 'The question text to display to users',
      },
    },
    {
      // Single topic per question (same `categories` collection as Articles).
      // Optional for backward compatibility: existing questions keep working and
      // show under "All topics" until an editor assigns a category.
      name: 'category',
      type: 'relationship',
      relationTo: 'categories',
      required: false,
      admin: {
        position: 'sidebar',
        description: 'Topic this question belongs to on the landing page (optional)',
      },
    },
    {
      name: 'order',
      type: 'number',
      required: true,
      defaultValue: 0,
      admin: {
        description: 'Display order (lower numbers appear first)',
      },
    },
    {
      name: 'isActive',
      type: 'checkbox',
      defaultValue: true,
      admin: {
        description: 'Whether this question should be displayed',
      },
    },
  ],
  timestamps: true,
}

