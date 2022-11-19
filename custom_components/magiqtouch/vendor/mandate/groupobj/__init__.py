class GroupObj(object):

    def __init__(self, group_data, cognito_obj):
        """
        :param group_data: a dictionary with information about a group
        :param cognito_obj: an instance of the Cognito class
        """
        self._data = group_data
        self._cognito = cognito_obj
        self.group_name = self._data.pop('GroupName', None)
        self.description = self._data.pop('Description', None)
        self.creation_date = self._data.pop('CreationDate', None)
        self.last_modified_date = self._data.pop('LastModifiedDate', None)
        self.role_arn = self._data.pop('RoleArn', None)
        self.precedence = self._data.pop('Precedence', None)

    def __unicode__(self):
        return self.group_name

    def __repr__(self):
        return '<{class_name}: {uni}>'.format(
            class_name=self.__class__.__name__, uni=self.__unicode__())
