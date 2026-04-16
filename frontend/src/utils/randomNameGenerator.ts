const ADJECTIVES = [
  'Shiny',
  'Sleek',
  'Modern',
  'Classic',
  'Compact',
  'Robust',
  'Smooth',
  'Solid',
  'Sharp',
  'Glossy',
  'Vibrant',
  'Epic',
  'Dynamic',
  'Gigantic',
  'Powerful',
  'Majestic',
  'Whimsical',
  'Fantastic',
  'Magnificent',
  'Magical',
  'Mystical',
  'Organic',
  'Stylish',
  'Intuitive',
  'Smart',
  'Efficient',
  'Reliable',
  'Secure',
  'Flexible',
  'Beautiful',
  'Sparkling',
  'Glowing',
  'Tremendous',
]

// Object-to-icon mapping using Phosphor icons
// Only includes objects with available icons from Phosphor set
const OBJECT_ICONS: Record<string, string> = {
  Rocket: 'ph-rocket',
  Light: 'ph-lightbulb',
  Crown: 'ph-crown',
  Target: 'ph-target',
  Star: 'ph-star',
  Diamond: 'ph-diamond',
  Flag: 'ph-flag',
  Gear: 'ph-gear',
  Book: 'ph-book',
  Palette: 'ph-palette',
  Fire: 'ph-fire',
  Lightning: 'ph-lightning',
  Planet: 'ph-planet',
  Cube: 'ph-cube',
  Shield: 'ph-shield',
  Compass: 'ph-compass',
  Phoenix: 'ph-fire-simple',
  Thunder: 'ph-cloud-lightning',
  Comet: 'ph-shooting-star',
  Heart: 'ph-heart',
  Leaf: 'ph-leaf',
  Airplane: 'ph-airplane',
  Cloud: 'ph-cloud',
  Sun: 'ph-sun',
  Moon: 'ph-moon',
  Mountain: 'ph-mountains',
  Sword: 'ph-sword',
  Anchor: 'ph-anchor',
  Flask: 'ph-flask',
  Archive: 'ph-archive',
  Battery: 'ph-battery-charging',
  Atom: 'ph-atom',
  Bell: 'ph-bell',
  Puzzle: 'ph-puzzle-piece',
  Trophy: 'ph-trophy',
  Eye: 'ph-eye',
  Camera: 'ph-camera',
  Note: 'ph-music-note',
  Tree: 'ph-tree',
  Flower: 'ph-flower',
  Magnet: 'ph-magnet',
  Key: 'ph-key',
  Lock: 'ph-lock',
  Feather: 'ph-feather',
  Butterfly: 'ph-butterfly',
  Ghost: 'ph-ghost',
  Lighthouse: 'ph-lighthouse',
  Tent: 'ph-tent',
  Bicycle: 'ph-bicycle',
  Hourglass: 'ph-hourglass',
}

// Only use objects that have icon mappings
const NOUNS = Object.keys(OBJECT_ICONS)

// Color palette for project avatars
const AVATAR_COLORS = [
  '#FF6B6B',
  '#4ECDC4',
  '#45B7D1',
  '#FFA07A',
  '#98D8C8',
  '#F7DC6F',
  '#BB8FCE',
  '#85C1E2',
  '#F06292',
  '#AED581',
  '#FF8A65',
  '#9575CD',
  '#52C41A',
  '#FF9800',
  '#2196F3',
  '#E91E63',
  '#26C6DA',
  '#FFAB91',
  '#5E35B1',
  '#A1887F',
  '#66BB6A',
  '#FFA726',
  '#42A5F5',
  '#EC407A',
]

export interface ProjectNameAndAvatar {
  name: string
  icon: string
  iconColor: string
}

export function generateProjectNameAndAvatar(): ProjectNameAndAvatar {
  const adjective = ADJECTIVES[Math.floor(Math.random() * ADJECTIVES.length)]
  const noun = NOUNS[Math.floor(Math.random() * NOUNS.length)]
  const icon = OBJECT_ICONS[noun]
  const iconColor = AVATAR_COLORS[Math.floor(Math.random() * AVATAR_COLORS.length)]

  return {
    name: `${adjective} ${noun}`,
    icon,
    iconColor,
  }
}

export { OBJECT_ICONS, AVATAR_COLORS }
