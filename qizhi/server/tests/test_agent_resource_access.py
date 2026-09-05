import unittest
from unittest.mock import AsyncMock, Mock

from agents.resource_access import get_owned_resource


class AgentResourceAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_query_is_scoped_to_resource_and_creator(self):
        scalar_result = Mock()
        scalar_result.first.return_value = None
        result = Mock()
        result.scalars.return_value = scalar_result
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        await get_owned_resource(db, "resource-123", "user-456")

        statement = db.execute.await_args.args[0]
        compiled = statement.compile()
        sql = str(compiled)
        params = compiled.params
        self.assertIn("resources.id", sql)
        self.assertIn("resources.creator_id", sql)
        self.assertIn("resource-123", params.values())
        self.assertIn("user-456", params.values())


if __name__ == "__main__":
    unittest.main()
