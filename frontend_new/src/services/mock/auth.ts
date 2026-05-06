import { adaptCurrentUser } from '../../adapters/auth';
import { currentUserRawMock } from '../../mocks/auth/currentUser.mock';
import type { User } from '../../types/auth';

export async function getCurrentUserMock(): Promise<User> {
  return adaptCurrentUser(currentUserRawMock);
}
