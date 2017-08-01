import os, re, random, hashlib, hmac, webapp2, jinja2, datetime
from string import letters
from config import *
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


# Create and validate cookies
def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(SECRET, val).hexdigest())


def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


# Main call to the datastore
class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    # Section for setting and reading cookies
    # Cookies expire when closing browser
    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    # Create user cookie for the current logged in user
    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    # Clear user cookie
    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    # Check to see if user is logged in or not
    # Checks if cookie is the same as the HASH in the datastore
    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


# Section for main page
class MainPage(BlogHandler):
    def get(self):
        self.render("index.html")


class BlogFront(BlogHandler):
    def get(self, title="", content="", username="", error=""):
        # Try & Catch to prevent errors when there are no posts
        try:
            # Get latest posts to the home page
            posts = db.GqlQuery("SELECT * FROM Post ORDER BY created DESC")

            # Get current logged in user
            if self.user:
                username = self.user.name
            # Format date as 10 Nov 2016
            # Check if Post contains any posts
            if posts:
                for post in posts:
                    date = str(post.created)
                    date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
                    date = date.strftime("%d %b %Y")
                    post_id = post.key().id()
                self.render("front.html", username=username, posts=posts, date=date)
            else:
                self.render("front.html", date=date, username=username)
        except Exception:
            self.render("front.html", username=username)


def make_salt():
    return ''.join(random.choice(letters) for x in xrange(SALT_LENGTH))


# Combine random string with SHA256
def make_pw_hash(name, pw, salt=None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)


def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)


def users_key(group='default'):
    return db.Key.from_path('users', group)


# Class for user entities
class User(db.Model):
    name = db.StringProperty(required=True)
    pw_hash = db.StringProperty(required=True)
    email = db.StringProperty()

    # Create objects before uploading to database
    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent=users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent=users_key(), name=name, pw_hash=pw_hash, email=email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


# Class for post entities
class Post(db.Model):
    title = db.StringProperty(required=True)
    image = db.StringProperty(required=False)
    content = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    username = db.StringProperty(required=True)
    comments = db.IntegerProperty()
    likes = db.IntegerProperty()

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        if self.user:
            return render_str("post.html", p=self, username=self.user.name)
        else:
            return render_str("post.html", p=self)


# Class for comments entities
class Comment(db.Model):
    post_id = db.IntegerProperty(required=True)
    username = db.StringProperty(required=True)
    comment = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)


# Class for likes entities
class Like(db.Model):
    post_id = db.IntegerProperty(required=True)
    username = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)


# Section to render post on permalink page
class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            liked = False
            likeId = None
            try:
                # Retrieve comments for a specific post
                comments = db.GqlQuery("SELECT * FROM Comment WHERE post_id ="
                                       + post_id + "ORDER BY created DESC LIMIT 20")
                # Retrieve likes for a specific post
                likes = db.GqlQuery("SELECT * FROM Like WHERE post_id=" + post_id)
                # Get created date and reformat the datetime format
                date = str(post.created)
                date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
                date = date.strftime("%d %b %Y")
            except Exception:
                pass

            if self.user:
                for like in likes:
                    if self.user.name == like.username:
                        liked = True
                        likeId = like.key().id()
                        break
                self.render("post.html",
                            post=post,
                            likes=likes,
                            comments=comments,
                            username=self.user.name,
                            date=date,
                            liked=liked,
                            likeId=likeId
                            )
            else:
                self.render("post.html", post=post, comments=comments, date=date)
        else:
            return self.redirect('/')


# Handler for editing a post
class EditPost(BlogHandler):
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            # Edit Post
            editTitle = self.request.get('editTitle')
            editImage = self.request.get('editImage')
            editContent = self.request.get('editContent')
            # Edit Post. Image parameter is optional
            if editTitle and editContent and self.user:
                if post.username == self.user.name:
                    post.image = editImage
                    post.title = editTitle
                    post.content = editContent
                    post.put()
                    return self.redirect('/post/' + post_id)
            else:
                return self.redirect('/post/' + post_id)
        else:
            return self.redirect('/')


# Handler for deleting a post
class DeletePost(BlogHandler):
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            deletePost = self.request.get('deletePost')
            if deletePost and self.user:
                if post.username == self.user.name:
                    # Delete all comments that belong to the post to be deleted
                    comments = Comment.all().filter('post_id =', int(post_id))
                    for comment in comments:
                        comment.delete()
                    post.delete()
                    return self.redirect('/post/' + post_id)
        else:
            return self.redirect('/')


# Handler for adding comments
class AddComment(BlogHandler):
    def post(self, post_id):
        # Return data of attributes from entity
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            # Values from input form
            # Create Post
            comment = self.request.get('content')

            # Add comments
            # Check if there is a logged in user and content is provided
            if comment and self.user:
                c = Comment(parent=blog_key(),
                            comment=comment,
                            username=self.user.name,
                            post_id=int(post_id)
                            )
                c.put()
                # Comments counter
                # Default value is None
                # If post has not comments, set it to one
                if post.comments is None:
                    post.comments = 1
                else:
                    post.comments = int(post.comments) + 1;
                # Update comments count
                post.put()
                return self.redirect('/post/' + post_id)
            else:
                return self.redirect('/post/' + post_id)
        else:
            return self.redirect('/')


# Handler for editing a comment
# Delete all post's comments
class EditComment(BlogHandler):
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            commentId = self.request.get('commentId')
            editComment = self.request.get('editComment')
            if commentId and editComment and self.user:
                key = db.Key.from_path('Comment', int(commentId), parent=blog_key())
                comment = db.get(key)
                if comment:
                    if comment.username == self.user.name:
                        comment.comment = editComment
                        comment.put()
                        return self.redirect('/post/' + post_id)
                else:
                    return self.redirect('/post/' + post_id)
            else:
                return self.redirect('/')
        else:
            return self.redirect('/')


# Handler for deleting a comment
class DeleteComment(BlogHandler):
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            commentId = self.request.get('commentId')
            # Retrieve current comment
            c_key = db.Key.from_path('Comment', int(commentId), parent=blog_key())
            comment = db.get(c_key)
            if comment:
                if commentId and self.user:
                    if comment.username:
                        comment.delete()
                        post.comments = int(post.comments) - 1
                        post.put()
                        return self.redirect('/post/' + post_id)
                    else:
                        return self.redirect('/post/' + post_id)
            else:
                return self.redirect('/')
        else:
            return self.redirect('/')


# Like Post
# Check if user is logged in and the logged in user
# is not the post author
class LikePost(BlogHandler):
    def post(self, post_id):
        # Retrieve current post
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            likePost = self.request.get('likePost')
            liked = False
            # Retrieve all likes belonging to a post
            likes = Like.all().filter('post_id =', int(post_id))
            # Check if logged in user has like the post
            if self.user:
                for like in likes:
                    if self.user.name == like.username:
                        liked = True
                        likeId = like.key().id()
                        break

            if likePost and self.user:
                if post.username != self.user.name and liked is False:
                    like = Like(parent=blog_key(), username=self.user.name, post_id=int(post_id))
                    like.put()
                    # Set counter to one if it has no likes when form is submitted
                    if post.likes is None:
                        post.likes = 1
                        post.put()
                        return self.redirect('/post/' + post_id)
                    else:
                        post.likes = int(post.likes) + 1
                        post.put()
                        return self.redirect('/post/' + post_id)
                else:
                    return self.redirect('/post/' + post_id)
        else:
            return self.redirect('/')


# Handler for unliking a post
class UnlikePost(BlogHandler):
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            unlikePost = self.request.get('unlikePost')
            liked = False
            # Retrieve all likes belonging to a post
            likes = Like.all().filter('post_id =', int(post_id))
            # Check if logged in user has like the post
            if self.user:
                for like in likes:
                    if self.user.name == like.username:
                        liked = True
                        likeId = like.key().id()
                        break

            if unlikePost and self.user and liked is True:
                u_key = db.Key.from_path('Like', int(unlikePost), parent=blog_key())
                like = db.get(u_key)
                # Delete like and decrease likes counter
                like.delete()
                post.likes = int(post.likes) - 1
                post.put()
                return self.redirect('/post/' + post_id)
            else:
                return self.redirect('/post/' + post_id)
        else:
            return self.redirect('/')


# Section for creating a new post
class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html", username=self.user.name)
        else:
            return self.redirect('/login')

    def post(self):
        if not self.user:
            return self.redirect('/login')

        # Values from input form
        title = self.request.get('title')
        content = self.request.get('content')
        username = self.user.name

        # Check if posts contains title, content and
        # Check if there is a logged in user
        if title and content and self.user:
            p = Post(parent=blog_key(),
                     title=title,
                     content=content,
                     username=username
                     )
            p.put()
            return self.redirect('/post/%s' % str(p.key().id()))
        else:
            error = "Title and content, please!"
            self.render("newpost.html",
                        title=title,
                        content=content,
                        error=error,
                        username=username
                        )


# Input Validation
USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return username and USER_RE.match(username)


PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return password and PASS_RE.match(password)


EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')


def valid_email(email):
    return not email or EMAIL_RE.match(email)


# Section for creating new user accounts
class SignUp(BlogHandler):
    def get(self):
        if self.user:
            return self.redirect('/')
        else:
            self.render("signup.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify_pass = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username, email=self.email)

        # Check if inputs are in a valid format
        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify_pass:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


# Section for registration
class Register(SignUp):
    def done(self):
        u = User.by_name(self.username)
        if u:
            msg = 'Username already exists.'
            self.render('signup.html', error_username=msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            # If registration is successful, log user in
            self.login(u)
            return self.redirect('/')


# Section for login
class Login(BlogHandler):
    def get(self):
        if self.user:
            return self.redirect('/')
        else:
            self.render('login.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')
        u = User.login(username, password)
        if u:
            self.login(u)
            return self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login.html', error=msg)


# Call logout function to clear user cookie
class Logout(BlogHandler):
    def get(self):
        self.logout()
        return self.redirect('/')


# Show registered users in users page
class Resume(BlogHandler):
    def get(self):
        self.render("resume.html")


app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/blog/?', BlogFront),
    ('/post/([0-9]+)', PostPage),
    ('/post/([0-9]+)/edit', EditPost),
    ('/post/([0-9]+)/delete', DeletePost),
    ('/post/([0-9]+)/addComment', AddComment),
    ('/post/([0-9]+)/editComment', EditComment),
    ('/post/([0-9]+)/deleteComment', DeleteComment),
    ('/post/([0-9]+)/like', LikePost),
    ('/post/([0-9]+)/unlike', UnlikePost),
    ('/newpost', NewPost),
    ('/signup', Register),
    ('/login', Login),
    ('/logout', Logout),
    ('/resume', Resume),
], debug=True)
