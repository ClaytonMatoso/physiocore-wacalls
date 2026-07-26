package main

func (u UserRow) HasRole(role string) bool {
	for _, candidate := range u.Roles {
		if candidate == role {
			return true
		}
	}
	return false
}
