import { connect } from 'react-redux';

import * as Action from '../actions';
import NewGroupForm from '../components/NewGroupForm';


const mapDispatchToProps = (dispatch, ownProps) => (
  {
    addNewGroup: formState => dispatch(
      Action.addNewGroup(formState)
    )
  }
);

export default connect(null, mapDispatchToProps)(NewGroupForm);
