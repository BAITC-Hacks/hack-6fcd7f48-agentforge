import { type Role, roleColor, roleLabel } from './api'

export default function RoleTag({ role }: { role: Role }) {
  return <span className="role-tag">
    <i style={{ backgroundColor: roleColor[role] }} />
    {roleLabel[role]}
  </span>
}
